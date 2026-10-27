<?php

namespace Tests\Unit;

use Tests\TestCase;

/**
 * Test that Blade templates correctly reference CSS modules using @vite directives
 * 
 * Validates Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 7.3
 */
class BladeTemplateCssReferencesTest extends TestCase
{
    /**
     * Test that guest layout loads base.css and guest layout CSS
     */
    public function test_guest_layout_loads_base_and_layout_css(): void
    {
        $layoutPath = resource_path('views/layouts/guest.blade.php');
        $this->assertFileExists($layoutPath, 'Guest layout file should exist');
        
        $content = file_get_contents($layoutPath);
        
        // Should load base.css
        $this->assertStringContainsString(
            "resources/css/base.css",
            $content,
            'Guest layout should reference base.css'
        );
        
        // Should load guest layout CSS
        $this->assertStringContainsString(
            "resources/css/layouts/guest.css",
            $content,
            'Guest layout should reference layouts/guest.css'
        );
        
        // Should have @yield('styles') for view-specific CSS
        $this->assertStringContainsString(
            "@yield('styles')",
            $content,
            'Guest layout should have @yield(\'styles\') section'
        );
        
        // Should NOT reference old guest.css directly
        $this->assertStringNotContainsString(
            "resources/css/guest.css'",
            $content,
            'Guest layout should not reference old guest.css'
        );
    }

    /**
     * Test that app layout loads base.css and app layout CSS
     */
    public function test_app_layout_loads_base_and_layout_css(): void
    {
        $layoutPath = resource_path('views/layouts/app.blade.php');
        $this->assertFileExists($layoutPath, 'App layout file should exist');
        
        $content = file_get_contents($layoutPath);
        
        // Should load base.css
        $this->assertStringContainsString(
            "resources/css/base.css",
            $content,
            'App layout should reference base.css'
        );
        
        // Should load app layout CSS
        $this->assertStringContainsString(
            "resources/css/layouts/app.css",
            $content,
            'App layout should reference layouts/app.css'
        );
        
        // Should have @yield('styles') for view-specific CSS
        $this->assertStringContainsString(
            "@yield('styles')",
            $content,
            'App layout should have @yield(\'styles\') section'
        );
        
        // Should NOT reference old app.css in the vite directive
        $this->assertStringNotContainsString(
            "resources/css/app.css'",
            $content,
            'App layout should not reference old app.css'
        );
    }

    /**
     * Test that login view loads its view-specific CSS
     */
    public function test_login_view_loads_view_specific_css(): void
    {
        $viewPath = resource_path('views/auth/login.blade.php');
        $this->assertFileExists($viewPath, 'Login view file should exist');
        
        $content = file_get_contents($viewPath);
        
        // Should extend guest layout
        $this->assertStringContainsString(
            "@extends('layouts.guest')",
            $content,
            'Login view should extend guest layout'
        );
        
        // Should have @section('styles') with login.css
        $this->assertStringContainsString(
            "@section('styles')",
            $content,
            'Login view should have @section(\'styles\')'
        );
        
        $this->assertStringContainsString(
            "resources/css/views/auth/login.css",
            $content,
            'Login view should reference views/auth/login.css'
        );
    }

    /**
     * Test that register view loads its view-specific CSS
     */
    public function test_register_view_loads_view_specific_css(): void
    {
        $viewPath = resource_path('views/auth/register.blade.php');
        $this->assertFileExists($viewPath, 'Register view file should exist');
        
        $content = file_get_contents($viewPath);
        
        // Should extend guest layout
        $this->assertStringContainsString(
            "@extends('layouts.guest')",
            $content,
            'Register view should extend guest layout'
        );
        
        // Should have @section('styles') with register.css
        $this->assertStringContainsString(
            "@section('styles')",
            $content,
            'Register view should have @section(\'styles\')'
        );
        
        $this->assertStringContainsString(
            "resources/css/views/auth/register.css",
            $content,
            'Register view should reference views/auth/register.css'
        );
    }

    /**
     * Test that dashboard view loads its view-specific CSS
     */
    public function test_dashboard_view_loads_view_specific_css(): void
    {
        $viewPath = resource_path('views/dashboard.blade.php');
        $this->assertFileExists($viewPath, 'Dashboard view file should exist');
        
        $content = file_get_contents($viewPath);
        
        // Should extend app layout
        $this->assertStringContainsString(
            "@extends('layouts.app')",
            $content,
            'Dashboard view should extend app layout'
        );
        
        // Should have @section('styles') with dashboard.css
        $this->assertStringContainsString(
            "@section('styles')",
            $content,
            'Dashboard view should have @section(\'styles\')'
        );
        
        $this->assertStringContainsString(
            "resources/css/views/dashboard.css",
            $content,
            'Dashboard view should reference views/dashboard.css'
        );
    }

    /**
     * Test that welcome view loads base.css and welcome.css
     */
    public function test_welcome_view_loads_base_and_view_css(): void
    {
        $viewPath = resource_path('views/welcome.blade.php');
        $this->assertFileExists($viewPath, 'Welcome view file should exist');
        
        $content = file_get_contents($viewPath);
        
        // Welcome doesn't extend a layout, so it should load base.css directly
        $this->assertStringContainsString(
            "resources/css/base.css",
            $content,
            'Welcome view should reference base.css'
        );
        
        // Should load welcome.css
        $this->assertStringContainsString(
            "resources/css/views/welcome.css",
            $content,
            'Welcome view should reference views/welcome.css'
        );
        
        // Should NOT reference old app.css
        $this->assertStringNotContainsString(
            "resources/css/app.css'",
            $content,
            'Welcome view should not reference old app.css'
        );
    }

    /**
     * Test that views do not load CSS modules from other views
     * This validates Requirement 5.5 - View CSS Isolation
     */
    public function test_views_do_not_load_other_view_css_modules(): void
    {
        // Login should not load register, dashboard, or welcome CSS
        $loginContent = file_get_contents(resource_path('views/auth/login.blade.php'));
        $this->assertStringNotContainsString('register.css', $loginContent);
        $this->assertStringNotContainsString('dashboard.css', $loginContent);
        $this->assertStringNotContainsString('welcome.css', $loginContent);
        
        // Register should not load login, dashboard, or welcome CSS
        $registerContent = file_get_contents(resource_path('views/auth/register.blade.php'));
        $this->assertStringNotContainsString('login.css', $registerContent);
        $this->assertStringNotContainsString('dashboard.css', $registerContent);
        $this->assertStringNotContainsString('welcome.css', $registerContent);
        
        // Dashboard should not load login, register, or welcome CSS
        $dashboardContent = file_get_contents(resource_path('views/dashboard.blade.php'));
        $this->assertStringNotContainsString('login.css', $dashboardContent);
        $this->assertStringNotContainsString('register.css', $dashboardContent);
        $this->assertStringNotContainsString('welcome.css', $dashboardContent);
        
        // Welcome should not load login, register, or dashboard CSS
        $welcomeContent = file_get_contents(resource_path('views/welcome.blade.php'));
        $this->assertStringNotContainsString('login.css', $welcomeContent);
        $this->assertStringNotContainsString('register.css', $welcomeContent);
        $this->assertStringNotContainsString('dashboard.css', $welcomeContent);
    }

    /**
     * Test that all views use @vite directive for CSS loading
     */
    public function test_all_views_use_vite_directive(): void
    {
        $views = [
            'layouts/guest.blade.php',
            'layouts/app.blade.php',
            'auth/login.blade.php',
            'auth/register.blade.php',
            'dashboard.blade.php',
            'welcome.blade.php',
        ];
        
        foreach ($views as $view) {
            $viewPath = resource_path("views/{$view}");
            $content = file_get_contents($viewPath);
            
            $this->assertStringContainsString(
                '@vite',
                $content,
                "View {$view} should use @vite directive for CSS loading"
            );
        }
    }

    /**
     * Test that layout templates load JavaScript along with CSS
     */
    public function test_layouts_load_javascript(): void
    {
        $guestContent = file_get_contents(resource_path('views/layouts/guest.blade.php'));
        $this->assertStringContainsString(
            'resources/js/app.js',
            $guestContent,
            'Guest layout should load app.js'
        );
        
        $appContent = file_get_contents(resource_path('views/layouts/app.blade.php'));
        $this->assertStringContainsString(
            'resources/js/app.js',
            $appContent,
            'App layout should load app.js'
        );
        
        $welcomeContent = file_get_contents(resource_path('views/welcome.blade.php'));
        $this->assertStringContainsString(
            'resources/js/app.js',
            $welcomeContent,
            'Welcome view should load app.js'
        );
    }
}
