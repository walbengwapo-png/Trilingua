<?php

namespace Tests\Unit;

use Tests\TestCase;

class TranslationReconciliationScheduleTest extends TestCase
{
    public function test_stale_translation_reconciliation_is_scheduled_with_terminal_updates_enabled(): void
    {
        $bootstrap = file_get_contents(base_path('bootstrap/app.php'));

        $this->assertIsString($bootstrap);
        $this->assertStringContainsString("translations:reconcile --fail", $bootstrap);
        $this->assertStringContainsString('everyFiveMinutes()', $bootstrap);
        $this->assertStringContainsString('withoutOverlapping()', $bootstrap);
    }
}
