<?php

namespace Tests\Unit;

use PHPUnit\Framework\TestCase;

class ViteConfigTest extends TestCase
{
    private string $viteConfigPath;
    private string $viteConfigContent;

    protected function setUp(): void
    {
        parent::setUp();
        // Calculate base path relative to the test file location
        $this->viteConfigPath = dirname(__DIR__, 2) . '/vite.config.js';
        
        if (!file_exists($this->viteConfigPath)) {
            $this->fail("vite.config.js file does not exist at {$this->viteConfigPath}");
        }
        
        $this->viteConfigContent = file_get_contents($this->viteConfigPath);
    }

    /**
     * Test that vite.config.js contains base.css as input entry
     * 
     * **Validates: Requirements 4.1, 4.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_contains_base_css_input(): void
    {
        $this->assertStringContainsString(
            "'resources/css/base.css'",
            $this->viteConfigContent,
            'vite.config.js should contain resources/css/base.css as input entry'
        );
    }

    /**
     * Test that vite.config.js contains layouts/app.css as input entry
     * 
     * **Validates: Requirements 4.1, 4.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_contains_layouts_app_css_input(): void
    {
        $this->assertStringContainsString(
            "'resources/css/layouts/app.css'",
            $this->viteConfigContent,
            'vite.config.js should contain resources/css/layouts/app.css as input entry'
        );
    }

    /**
     * Test that vite.config.js contains layouts/guest.css as input entry
     * 
     * **Validates: Requirements 4.1, 4.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_contains_layouts_guest_css_input(): void
    {
        $this->assertStringContainsString(
            "'resources/css/layouts/guest.css'",
            $this->viteConfigContent,
            'vite.config.js should contain resources/css/layouts/guest.css as input entry'
        );
    }

    /**
     * Test that vite.config.js contains views/auth/login.css as input entry
     * 
     * **Validates: Requirements 4.1, 4.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_contains_views_auth_login_css_input(): void
    {
        $this->assertStringContainsString(
            "'resources/css/views/auth/login.css'",
            $this->viteConfigContent,
            'vite.config.js should contain resources/css/views/auth/login.css as input entry'
        );
    }

    /**
     * Test that vite.config.js contains views/auth/register.css as input entry
     * 
     * **Validates: Requirements 4.1, 4.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_contains_views_auth_register_css_input(): void
    {
        $this->assertStringContainsString(
            "'resources/css/views/auth/register.css'",
            $this->viteConfigContent,
            'vite.config.js should contain resources/css/views/auth/register.css as input entry'
        );
    }

    /**
     * Test that vite.config.js contains views/dashboard.css as input entry
     * 
     * **Validates: Requirements 4.1, 4.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_contains_views_dashboard_css_input(): void
    {
        $this->assertStringContainsString(
            "'resources/css/views/dashboard.css'",
            $this->viteConfigContent,
            'vite.config.js should contain resources/css/views/dashboard.css as input entry'
        );
    }

    /**
     * Test that vite.config.js contains views/welcome.css as input entry
     * 
     * **Validates: Requirements 4.1, 4.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_contains_views_welcome_css_input(): void
    {
        $this->assertStringContainsString(
            "'resources/css/views/welcome.css'",
            $this->viteConfigContent,
            'vite.config.js should contain resources/css/views/welcome.css as input entry'
        );
    }

    /**
     * Test that vite.config.js maintains JavaScript entry point
     * 
     * **Validates: Requirements 4.5**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_maintains_javascript_entry_point(): void
    {
        $this->assertStringContainsString(
            "'resources/js/app.js'",
            $this->viteConfigContent,
            'vite.config.js should maintain resources/js/app.js as input entry'
        );
    }

    /**
     * Test that vite.config.js contains all CSS module entries
     * 
     * **Validates: Requirements 4.1**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_contains_all_css_module_entries(): void
    {
        $requiredCssModules = [
            'resources/css/base.css',
            'resources/css/layouts/app.css',
            'resources/css/layouts/guest.css',
            'resources/css/views/auth/login.css',
            'resources/css/views/auth/register.css',
            'resources/css/views/dashboard.css',
            'resources/css/views/welcome.css',
        ];

        foreach ($requiredCssModules as $module) {
            $this->assertStringContainsString(
                "'{$module}'",
                $this->viteConfigContent,
                "vite.config.js should contain {$module} as input entry"
            );
        }
    }

    /**
     * Test that vite.config.js contains laravel plugin configuration
     * 
     * **Validates: Requirements 4.1**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_contains_laravel_plugin(): void
    {
        $this->assertStringContainsString(
            'laravel({',
            $this->viteConfigContent,
            'vite.config.js should contain laravel plugin configuration'
        );

        $this->assertStringContainsString(
            'input:',
            $this->viteConfigContent,
            'vite.config.js should contain input configuration'
        );
    }

    /**
     * Test that vite.config.js contains refresh configuration
     * 
     * **Validates: Requirements 4.4**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_contains_refresh_configuration(): void
    {
        $this->assertStringContainsString(
            'refresh: true',
            $this->viteConfigContent,
            'vite.config.js should contain refresh: true for hot module replacement'
        );
    }

    /**
     * Test that vite.config.js contains Tailwind CSS plugin
     * 
     * **Validates: Requirements 6.1**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_contains_tailwind_plugin(): void
    {
        $this->assertStringContainsString(
            'tailwindcss()',
            $this->viteConfigContent,
            'vite.config.js should contain tailwindcss plugin'
        );
    }

    /**
     * Test that vite.config.js imports required dependencies
     * 
     * **Validates: Requirements 4.1**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_imports_required_dependencies(): void
    {
        $requiredImports = [
            "import { defineConfig } from 'vite'",
            "import laravel from 'laravel-vite-plugin'",
            "import tailwindcss from '@tailwindcss/vite'",
        ];

        foreach ($requiredImports as $import) {
            $this->assertStringContainsString(
                $import,
                $this->viteConfigContent,
                "vite.config.js should contain import: {$import}"
            );
        }
    }

    /**
     * Test that vite.config.js file is not empty
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_is_not_empty(): void
    {
        $this->assertNotEmpty(
            trim($this->viteConfigContent),
            'vite.config.js should not be empty'
        );
    }

    /**
     * Test that vite.config.js has valid JavaScript syntax (basic check)
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_has_balanced_braces(): void
    {
        $openBraces = substr_count($this->viteConfigContent, '{');
        $closeBraces = substr_count($this->viteConfigContent, '}');
        
        $this->assertEquals(
            $openBraces,
            $closeBraces,
            'vite.config.js should have balanced opening and closing braces'
        );
    }

    /**
     * Test that vite.config.js has balanced brackets
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_has_balanced_brackets(): void
    {
        $openBrackets = substr_count($this->viteConfigContent, '[');
        $closeBrackets = substr_count($this->viteConfigContent, ']');
        
        $this->assertEquals(
            $openBrackets,
            $closeBrackets,
            'vite.config.js should have balanced opening and closing brackets'
        );
    }

    /**
     * Test that vite.config.js exports default configuration
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('vite-config')]
    public function test_vite_config_exports_default_configuration(): void
    {
        $this->assertStringContainsString(
            'export default defineConfig',
            $this->viteConfigContent,
            'vite.config.js should export default configuration using defineConfig'
        );
    }
}
