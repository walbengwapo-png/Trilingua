<?php

namespace Tests\Unit;

use App\Support\PreviewUrl;
use PHPUnit\Framework\TestCase;

class PreviewUrlTest extends TestCase
{
    public function test_active_urls_and_attribute_injections_are_rejected(): void
    {
        foreach (['javascript:parent.bad=1', 'data:text/html,<script>bad</script>', '//evil.example/file', '/a" onload="bad', "\x00javascript:bad", '<img src=x onerror=bad>'] as $url) {
            $this->assertSame('about:blank', PreviewUrl::pdf($url));
        }
    }

    public function test_application_paths_and_signed_storage_urls_are_retained(): void
    {
        foreach (['/history/1/file', 'https://storage.example/file.pdf?token=abc&x=1', 'http://localhost/file.pdf'] as $url) {
            $this->assertSame($url, PreviewUrl::pdf($url));
        }
    }
}
