<?php

namespace Tests\Unit;

use App\Http\Controllers\TranslationController;
use App\Http\Controllers\NotificationController;
use App\Models\TranslationHistory;
use App\Services\StorageService;
use App\Services\Translation\CompletedDownloadResolver;
use Illuminate\Config\Repository;
use Illuminate\Container\Container;
use Illuminate\Contracts\View\Factory;
use Illuminate\Contracts\View\View;
use Illuminate\Database\Capsule\Manager as Capsule;
use Illuminate\Database\Eloquent\ModelNotFoundException;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Events\Dispatcher;
use Illuminate\Http\Request;
use Illuminate\Notifications\DatabaseNotification;
use Illuminate\Routing\Router;
use Illuminate\Routing\UrlGenerator;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Facade;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Route;
use PHPUnit\Framework\TestCase;

/** Real owner-scoped SQL and named routes, without the blocked application bootstrap. */
class TranslationNavigationTest extends TestCase
{
    private array $rendered = [];
    private const OWN = '40872971-81cc-4f22-9196-d8567ba459a4';
    private const OTHER = 'a06ca037-2bdb-4a2d-8a68-fd8c04dc3324';

    protected function setUp(): void
    {
        parent::setUp();
        $app = new Container; Container::setInstance($app);
        $app->instance('config', new Repository(['translation' => ['languages' => ['English', 'Cebuano', 'Filipino'], 'supported_formats' => ['docx']]]));
        Facade::setFacadeApplication($app); Facade::clearResolvedInstances();
        Auth::swap(new class {
            public function id(): int { return 1; }
            public function user(): object { return (object) ['id' => 1, 'is_admin' => false]; }
        });
        Log::swap(new \Psr\Log\NullLogger);
        $router = new Router(new Dispatcher($app), $app); Route::swap($router);
        require dirname(__DIR__, 2).'/routes/web.php';
        $router->getRoutes()->refreshNameLookups();
        $app->instance('url', new UrlGenerator($router->getRoutes(), Request::create('https://trilingua.test')));
        $capsule = new Capsule($app);
        $capsule->addConnection(['driver' => 'sqlite', 'database' => ':memory:', 'prefix' => '']);
        $capsule->setAsGlobal(); $capsule->bootEloquent(); DB::swap($capsule->getDatabaseManager());
        DB::connection()->getSchemaBuilder()->create('translation_jobs', function (Blueprint $table): void {
            $table->id(); $table->integer('user_id'); $table->string('uuid'); $table->string('status'); $table->string('original_name');
        });
        DB::table('translation_jobs')->insert([
            ['id' => 1, 'user_id' => 1, 'uuid' => self::OWN, 'status' => 'queued', 'original_name' => 'lesson.docx'],
            ['id' => 2, 'user_id' => 2, 'uuid' => self::OTHER, 'status' => 'processing', 'original_name' => 'private.docx'],
        ]);
        $factory = $this->createMock(Factory::class);
        $view = $this->createMock(View::class);
        $factory->method('make')->willReturnCallback(function ($name, $data) use ($view) {
            $this->assertSame('translation', $name); $this->rendered = $data; return $view;
        });
        $app->instance(Factory::class, $factory);
    }

    protected function tearDown(): void
    {
        DB::disconnect(); Facade::clearResolvedInstances(); Facade::setFacadeApplication(null); Container::setInstance(null);
        parent::tearDown();
    }

    private function show(array $query = []): void
    {
        $controller = (new \ReflectionClass(TranslationController::class))->newInstanceWithoutConstructor();
        $controller->show(Request::create('/translate', 'GET', $query));
    }

    public function test_new_tab_resumes_only_the_authenticated_users_active_job(): void
    {
        $this->show();
        $this->assertSame(['id' => self::OWN, 'filename' => 'lesson.docx'], $this->rendered['initialJob']);
        $this->assertSame(1, $this->rendered['viewerId']);
    }

    public function test_tracking_link_can_reopen_its_completed_job(): void
    {
        DB::table('translation_jobs')->where('id', 1)->update(['status' => 'completed']);
        $this->show(['job' => self::OWN]);
        $this->assertSame(self::OWN, $this->rendered['initialJob']['id']);
    }

    public function test_tracking_url_cannot_select_another_users_job(): void
    {
        $this->expectException(ModelNotFoundException::class);
        $this->show(['job' => self::OTHER]);
    }

    public function test_completed_payloads_link_to_the_html_page_including_when_the_file_is_missing(): void
    {
        $history = (new TranslationHistory)->forceFill(['id' => 26, 'storage_backend' => StorageService::BACKEND_SUPABASE,
            'storage_path' => 'fixture/output.docx', 'translated_filename' => 'output.docx']);
        $storage = $this->createMock(StorageService::class);
        $storage->method('generateSignedUrl')->willReturn(['signed_url' => 'https://files.invalid/result', 'signed_url_expires_at' => '2099-01-01']);
        $payload = (new CompletedDownloadResolver($storage))->resolve($history);
        $this->assertSame('https://trilingua.test/history/26/view', $payload['view_url']);
        $this->assertSame('completed', $payload['status']);
        $storage = $this->createMock(StorageService::class);
        $storage->method('generateSignedUrl')->willThrowException(new \RuntimeException('Synthetic outage'));
        $storage->method('exists')->willReturn(StorageService::PRESENCE_MISSING);
        $payload = (new CompletedDownloadResolver($storage))->resolve($history);
        $this->assertSame('https://trilingua.test/history/26/view', $payload['view_url']);
        $this->assertSame('failed', $payload['status']);
        $this->assertArrayNotHasKey('download_url', $payload);
    }

    public function test_completion_notification_opens_the_html_result_directly(): void
    {
        $notification = (new DatabaseNotification)->forceFill(['type' => \App\Notifications\TranslationCompleted::class, 'data' => ['translation_id' => 26]]);
        $method = new \ReflectionMethod(NotificationController::class, 'targetUrl');
        $this->assertSame('https://trilingua.test/history/26/view', $method->invoke(new NotificationController, $notification));
    }

    public function test_translation_screen_compiles_with_real_route_declarations_and_one_status_card(): void
    {
        $this->show();
        extract($this->rendered);
        $__env = new \Illuminate\View\Factory(new \Illuminate\View\Engines\EngineResolver,
            new \Illuminate\View\FileViewFinder(new \Illuminate\Filesystem\Filesystem, []), new Dispatcher(app()));
        $compiler = new \Illuminate\View\Compilers\BladeCompiler(new \Illuminate\Filesystem\Filesystem, sys_get_temp_dir());
        $source = file_get_contents(dirname(__DIR__, 2).'/resources/views/translation.blade.php');
        $start = strpos($source, "@section('content')") + strlen("@section('content')");
        $compiled = $compiler->compileString(substr($source, $start, strrpos($source, '@endsection') - $start));
        ob_start();
        try { eval('?>'.$compiled); $html = ob_get_contents(); }
        finally { ob_end_clean(); }
        $this->assertSame(1, substr_count($html, 'id="translate-progress"'));
        $this->assertStringContainsString('href="https://trilingua.test/history"', $html);
        preg_match('/var ROUTES = (.+);/', $html, $match);
        $routes = json_decode($match[1], true, 32, JSON_THROW_ON_ERROR);
        $this->assertSame('https://trilingua.test/translate?job=__JOB__', $routes['track']);
        $this->assertSame('https://trilingua.test/translate/status/__JOB__', $routes['status']);
    }
}
