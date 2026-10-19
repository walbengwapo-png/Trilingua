<?php

namespace Tests\Feature;

use App\Models\User;
use App\Services\StorageService;
use App\Support\WorkbookWarnings;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Http;
use Mockery;
use Tests\TestCase;
use ZipArchive;

class WorkbookWarningsTest extends TestCase
{
    use RefreshDatabase;

    private function workbook(bool $unsupported): string
    {
        $path = tempnam(sys_get_temp_dir(), 'workbook-');
        $zip = new ZipArchive;
        $zip->open($path, ZipArchive::CREATE | ZipArchive::OVERWRITE);
        $zip->addFromString('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/>'.($unsupported ? '<extLst><ext uri="fixture"/></extLst>' : '<dataValidations/><conditionalFormatting/>').'</worksheet>');
        $zip->addFromString('xl/drawings/drawing1.xml', '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing">'.($unsupported ? '<xdr:sp/>' : '<xdr:pic/><xdr:graphicFrame/>').'</xdr:wsDr>');
        $zip->close();

        return $path;
    }

    public function test_shapes_and_extensions_are_reported_but_basic_features_are_not(): void
    {
        foreach ([false, true] as $unsupported) {
            $path = $this->workbook($unsupported);
            try {
                $warnings = WorkbookWarnings::inspect($path);
                $this->assertCount($unsupported ? 2 : 0, $warnings);
                if ($unsupported) {
                    $this->assertStringContainsString('drawing shapes', $warnings[0]);
                    $this->assertStringContainsString('extension data', $warnings[1]);
                }
            } finally { unlink($path); }
        }
    }

    public function test_upload_returns_visible_warnings_and_still_queues_work(): void
    {
        Http::preventStrayRequests();
        config(['queue.default' => 'database']);
        $user = User::factory()->create();
        $storage = Mockery::mock(StorageService::class);
        $storage->shouldReceive('uploadWithFallback')->once()->andReturn([
            'backend' => 'local', 'storage_path' => 'fixture/original.xlsx', 'signed_url' => '/fixture', 'signed_url_expires_at' => null,
        ]);
        $this->app->instance(StorageService::class, $storage);
        $path = $this->workbook(true);
        try {
            $response = $this->actingAs($user)->postJson('/translate', [
                'source_lang' => 'English', 'target_lang' => 'Cebuano',
                'document' => new UploadedFile($path, 'worksheet.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', null, true),
            ]);
            $response->assertOk()->assertJsonPath('status', 'processing')->assertJsonCount(2, 'warnings');
            $this->assertDatabaseCount('jobs', 1);
            $this->actingAs($user)->get('/translate')->assertOk()->assertSee('id="workbook-warning"', false);
        } finally { if (file_exists($path)) unlink($path); }
    }
}
