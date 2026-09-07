<?php

namespace Tests\Unit;

use Tests\TestCase;

class TranslationReconciliationScheduleTest extends TestCase
{
    public function test_stale_translation_reconciliation_is_scheduled_with_terminal_updates_enabled(): void
    {
        $routes = file_get_contents(base_path('routes/console.php'));

        $this->assertIsString($routes);
        $this->assertStringContainsString("translations:reconcile --fail", $routes);
        $this->assertStringContainsString('everyFiveMinutes()', $routes);
        $this->assertStringContainsString('withoutOverlapping()', $routes);
    }
}
