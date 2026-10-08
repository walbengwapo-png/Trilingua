<?php

namespace Tests\Unit;

use Illuminate\Support\Facades\Artisan;
use Tests\TestCase;

class ValidateDeploymentTimeoutsTest extends TestCase
{
    public function test_default_ladder_passes_validation(): void
    {
        config(['timeouts.python_service' => 1200]);
        config(['timeouts.job' => 1300]);
        config(['timeouts.worker' => 1500]);
        config(['timeouts.retry_after' => 1800]);
        config(['timeouts.reconcile_processing' => 2100]);
        config(['timeouts.check_stale' => 2100]);

        $this->assertSame(0, Artisan::call('deployment:validate-timeouts'));
    }

    public function test_retry_after_below_worker_timeout_fails_validation(): void
    {
        config(['timeouts.python_service' => 1200]);
        config(['timeouts.job' => 1300]);
        config(['timeouts.worker' => 1500]);
        config(['timeouts.retry_after' => 900]);
        config(['timeouts.reconcile_processing' => 2100]);
        config(['timeouts.check_stale' => 2100]);

        $this->assertSame(1, Artisan::call('deployment:validate-timeouts'));
        $output = Artisan::output();
        $this->assertStringContainsString('retry_after', $output);
    }

    public function test_reconcile_below_retry_after_fails_validation(): void
    {
        config(['timeouts.python_service' => 1200]);
        config(['timeouts.job' => 1300]);
        config(['timeouts.worker' => 1500]);
        config(['timeouts.retry_after' => 1800]);
        config(['timeouts.reconcile_processing' => 1500]);
        config(['timeouts.check_stale' => 2100]);

        $this->assertSame(1, Artisan::call('deployment:validate-timeouts'));
        $output = Artisan::output();
        $this->assertStringContainsString('reconcile_processing', $output);
    }
}