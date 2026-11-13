<?php

namespace Tests\Unit;

use Illuminate\Container\Container;
use Illuminate\Events\Dispatcher;
use Illuminate\Http\Request;
use Illuminate\Routing\Router;
use Illuminate\Routing\UrlGenerator;
use Illuminate\Support\Facades\Facade;
use Illuminate\Support\Facades\Route;
use Illuminate\View\Compilers\BladeCompiler;
use Illuminate\Filesystem\Filesystem;
use PHPUnit\Framework\TestCase;

/** Uses the real route definitions and dashboard row markup, without a database. */
class DashboardRecentLinkTest extends TestCase
{
    public function test_document_and_text_links_target_the_html_route_and_json_route_remains(): void
    {
        $app = new Container; Container::setInstance($app); Facade::setFacadeApplication($app);
        $router = new Router(new Dispatcher($app), $app);
        Route::swap($router);
        try {
            require dirname(__DIR__, 2).'/routes/web.php';
            $routes = $router->getRoutes(); $routes->refreshNameLookups();
            $app->instance('url', new UrlGenerator($routes, Request::create('https://trilingua.test')));
            $viewRoute = $routes->getByName('history.view');
            $this->assertSame('history/{id}/view', $viewRoute->uri());
            $this->assertSame('history/{id}', $routes->getByName('history.detail')->uri());
            $this->assertNotSame($viewRoute->getActionName(), $routes->getByName('history.detail')->getActionName());

            $template = file_get_contents(dirname(__DIR__, 2).'/resources/views/dashboard.blade.php');
            preg_match('/<a href="\{\{ route\(\x27history\.[^<]+?<\/a>/s', $template, $match);
            $this->assertNotEmpty($match, 'Dashboard recent-row anchor was not found');
            $compiler = new BladeCompiler(new Filesystem, sys_get_temp_dir());
            $compiled = $compiler->compileString($match[0]);
            foreach (['document', 'text'] as $type) {
                $record = ['id' => 26, 'translation_type' => $type, 'original_filename' => 'source.docx', 'source_text' => 'Good morning'];
                ob_start();
                try { eval('?>'.$compiled); $html = ob_get_contents(); }
                finally { ob_end_clean(); }
                $this->assertStringContainsString('https://trilingua.test/history/26/view', $html);
                $this->assertStringContainsString($type === 'document' ? 'source.docx' : 'Good morning', $html);
            }
        } finally {
            Facade::clearResolvedInstances(); Facade::setFacadeApplication(null); Container::setInstance(null);
        }
    }
}
