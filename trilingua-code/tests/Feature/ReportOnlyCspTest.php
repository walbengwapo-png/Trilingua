<?php

namespace Tests\Feature;

use Tests\TestCase;

class ReportOnlyCspTest extends TestCase
{
    public function test_strict_script_policy_is_observational_and_enforced_policy_is_unchanged(): void
    {
        $response = $this->get('/login');
        $response->assertOk()->assertHeader('Content-Security-Policy-Report-Only', "script-src 'self'; script-src-attr 'none';");
        $this->assertSame(
            "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: https: blob:; font-src 'self' data: https://fonts.gstatic.com; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'self';",
            $response->headers->get('Content-Security-Policy')
        );
    }
}
