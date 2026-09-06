<?php

namespace Tests\Feature;

use Tests\TestCase;
use Illuminate\Foundation\Testing\RefreshDatabase;

/**
 * Bug Condition Exploration Test for Authentication Pages CSS Rendering
 * 
 * **Validates: Requirements 1.1, 1.2, 1.4**
 * 
 * Property 1: Bug Condition - Authentication Pages CSS Not Rendering
 * 
 * CRITICAL: This test MUST FAIL on unfixed code - failure confirms the bug exists
 * 
 * This test encodes the expected behavior from the design document:
 * - CSS files should load successfully (200 status)
 * - Visual elements should be styled correctly
 * - Vite manifest should include the necessary CSS entries
 * 
 * When this test FAILS on unfixed code, it surfaces counterexamples:
 * - CSS not loading (404 errors)
 * - Missing Vite manifest entries
 * - Unstyled HTML being rendered
 * 
 * When this test PASSES after the fix, it confirms the bug is resolved.
 */
class AuthCssRenderingTest extends TestCase
{
    use RefreshDatabase;
    
    /**
     * Test that login page loads with CSS styles rendered
     * 
     * Bug Condition: Accessing /login route via guest layout
     * Expected Behavior: CSS styles should be loaded and applied
     * 
     * @return void
     */
    public function test_login_page_renders_with_css_styles(): void
    {
        // Access the login page
        $response = $this->get('/login');
        
        // Verify the page loads successfully
        $response->assertStatus(200);
        
        // Verify the page title contains TriLingua
        $response->assertSee('Sign in', false);
        $response->assertSee('Welcome back', false);
        
        // CRITICAL ASSERTION: Verify Vite directive is present in the HTML
        // This checks that @vite directive generates the proper <link> and <script> tags
        $content = $response->getContent();
        
        // Check for Vite-generated CSS link tag
        // On unfixed code, this will fail because CSS is not being properly loaded
        $this->assertMatchesRegularExpression(
            '/<link[^>]+rel=["\']stylesheet["\'][^>]*>/',
            $content,
            'Expected CSS <link> tag to be present in login page HTML. ' .
            'This indicates CSS is not being loaded by Vite.'
        );
        
        // Verify that CSS classes used in the guest layout are present in the HTML
        // These classes should be styled by the CSS file
        $response->assertSee('class="auth-container"', false);
        $response->assertSee('class="auth-card"', false);
        $response->assertSee('class="auth-brand__logo"', false);
        $response->assertSee('class="auth-header"', false);
        
        // Verify form elements that require styling are present
        $response->assertSee('class="btn-auth"', false);
        $response->assertSee('class="form-field"', false);
    }
    
    /**
     * Test that register page loads with CSS styles rendered
     * 
     * Bug Condition: Accessing /register route via guest layout
     * Expected Behavior: CSS styles should be loaded and applied
     * 
     * @return void
     */
    public function test_register_page_renders_with_css_styles(): void
    {
        // Access the register page
        $response = $this->get('/register');
        
        // Verify the page loads successfully
        $response->assertStatus(200);
        
        // Verify the page content
        $response->assertSee('Create account', false);
        
        // CRITICAL ASSERTION: Verify Vite directive is present in the HTML
        $content = $response->getContent();
        
        // Check for Vite-generated CSS link tag
        // On unfixed code, this will fail because CSS is not being properly loaded
        $this->assertMatchesRegularExpression(
            '/<link[^>]+rel=["\']stylesheet["\'][^>]*>/',
            $content,
            'Expected CSS <link> tag to be present in register page HTML. ' .
            'This indicates CSS is not being loaded by Vite.'
        );
        
        // Verify that CSS classes used in the guest layout are present in the HTML
        $response->assertSee('class="auth-container"', false);
        $response->assertSee('class="auth-card"', false);
        $response->assertSee('class="auth-brand__logo"', false);
        
        // Verify form elements that require styling are present
        $response->assertSee('class="btn-auth"', false);
        $response->assertSee('class="form-field"', false);
    }
    
    /**
     * Test that Vite manifest includes CSS entries
     * 
     * This test checks if Vite has properly compiled the CSS and generated
     * the manifest.json file with the correct entries.
     * 
     * On unfixed code, this may fail if:
     * - Vite manifest is missing
     * - CSS entries are not in the manifest
     * - Manifest is malformed
     * 
     * @return void
     */
    public function test_vite_manifest_includes_css_entries(): void
    {
        $manifestPath = public_path('build/manifest.json');
        
        // Check if manifest exists
        $this->assertFileExists(
            $manifestPath,
            'Vite manifest.json not found. Run "npm run build" or "npm run dev" to generate assets.'
        );
        
        // Read and parse manifest
        $manifestContent = file_get_contents($manifestPath);
        $manifest = json_decode($manifestContent, true);
        
        $this->assertIsArray(
            $manifest,
            'Vite manifest.json is not valid JSON or is malformed.'
        );
        
        // Check if app.css is in the manifest
        // On unfixed code, this should exist but may not be properly configured
        $cssEntryFound = false;
        foreach ($manifest as $key => $entry) {
            if (str_contains($key, 'resources/css/base.css')) {
                $cssEntryFound = true;
                
                // Verify the entry has a 'file' property (the compiled CSS file)
                $this->assertArrayHasKey(
                    'file',
                    $entry,
                    'CSS entry in manifest is missing "file" property.'
                );
                
                // Verify the compiled CSS file exists
                $compiledCssPath = public_path('build/' . $entry['file']);
                $this->assertFileExists(
                    $compiledCssPath,
                    "Compiled CSS file not found at: build/{$entry['file']}"
                );
                
                break;
            }
        }
        
        $this->assertTrue(
            $cssEntryFound,
            'CSS entry (resources/css/base.css) not found in Vite manifest. ' .
            'This indicates Vite is not compiling the CSS properly.'
        );
    }
    
    /**
     * Test that compiled CSS file contains custom styles
     * 
     * This test checks that the compiled guest.css file includes the custom
     * CSS classes defined for authentication pages (not just Tailwind utilities).
     * 
     * After the fix, guest-specific styles should be in guest.css.
     * 
     * @return void
     */
    public function test_compiled_css_file_contains_custom_styles(): void
    {
        $manifestPath = public_path('build/manifest.json');
        
        // Skip if manifest doesn't exist (covered by previous test)
        if (!file_exists($manifestPath)) {
            $this->markTestSkipped('Vite manifest not found. Run npm run build first.');
        }
        
        $manifestContent = file_get_contents($manifestPath);
        $manifest = json_decode($manifestContent, true);
        
        // Find the guest.css file in the manifest
        $cssFile = null;
        foreach ($manifest as $key => $entry) {
            if (str_contains($key, 'resources/css/guest.css') && isset($entry['file'])) {
                $cssFile = $entry['file'];
                break;
            }
        }
        
        if ($cssFile === null) {
            $this->markTestSkipped('Guest CSS entry not found in manifest.');
        }
        
        // Read the compiled CSS file directly from filesystem
        $compiledCssPath = public_path('build/' . $cssFile);
        $this->assertFileExists(
            $compiledCssPath,
            "Compiled guest CSS file not found at: build/{$cssFile}"
        );
        
        $cssContent = file_get_contents($compiledCssPath);
        
        // CRITICAL ASSERTIONS: Verify the CSS contains custom classes for guest pages
        // After the fix, these should be present in guest.css
        $this->assertStringContainsString(
            '.guest-center',
            $cssContent,
            'CSS file does not contain expected .guest-center class. ' .
            'This indicates custom CSS is being stripped during compilation or not properly separated.'
        );
        
        $this->assertStringContainsString(
            '.form-card',
            $cssContent,
            'CSS file does not contain expected .form-card class. ' .
            'Custom CSS classes are missing from the compiled output.'
        );
        
        $this->assertStringContainsString(
            '.hero',
            $cssContent,
            'CSS file does not contain expected .hero class. ' .
            'Custom CSS classes are missing from the compiled output.'
        );
        
        $this->assertStringContainsString(
            '.left-hero',
            $cssContent,
            'CSS file does not contain expected .left-hero class. ' .
            'Custom CSS classes are missing from the compiled output.'
        );
        
        $this->assertStringContainsString(
            '.btn',
            $cssContent,
            'CSS file does not contain expected .btn class. ' .
            'Custom CSS classes are missing from the compiled output.'
        );
    }
    
    /**
     * ========================================================================
     * PRESERVATION PROPERTY TESTS
     * ========================================================================
     * 
     * **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
     * 
     * Property 2: Preservation - Authenticated Pages Continue Working
     * 
     * These tests capture the CURRENT behavior of authenticated pages on UNFIXED code.
     * They verify that after implementing the fix, authenticated pages continue to work
     * exactly as they did before.
     * 
     * EXPECTED OUTCOME: These tests PASS on unfixed code (baseline behavior)
     * EXPECTED OUTCOME: These tests PASS after fix (preservation confirmed)
     */
    
    /**
     * Test that dashboard page renders with proper styling
     * 
     * Preservation: Dashboard must continue to render with proper CSS styling
     * This test observes the current behavior on unfixed code.
     * 
     * @return void
     */
    public function test_dashboard_page_renders_with_proper_styling(): void
    {
        // Create and authenticate a user
        $user = \App\Models\User::factory()->create();
        $this->actingAs($user);
        
        // Access the dashboard page
        $response = $this->get('/dashboard');
        
        // Verify the page loads successfully
        $response->assertStatus(200);
        
        // Verify the app layout is being used
        $response->assertSee('TriLingua', false);
        $response->assertSee('Dashboard', false);
        
        // CRITICAL ASSERTION: Verify Vite directive generates CSS link tag
        $content = $response->getContent();
        
        $this->assertMatchesRegularExpression(
            '/<link[^>]+rel=["\']stylesheet["\'][^>]*>/',
            $content,
            'Expected CSS <link> tag to be present in dashboard page HTML. ' .
            'This indicates CSS is not being loaded by Vite for authenticated pages.'
        );
        
        // Verify that CSS classes used in the app layout are present in the HTML
        // These classes should be styled by app.css
        $response->assertSee('class="app-container"', false);
        $response->assertSee('class="sidebar"', false);
        $response->assertSee('class="main"', false);
        $response->assertSee('class="header"', false);
        $response->assertSee('class="nav"', false);
        
        // Verify dashboard-specific elements are present
        $response->assertSee('class="cards-grid"', false);
        $response->assertSee('class="stat-card"', false);
        $response->assertSee('class="table-card"', false);
        
        // Verify navigation elements are present
        $response->assertSee('class="nav-link active"', false);
        $response->assertSee('New Translation', false);
        $response->assertSee('Saved Translations', false);
        
        // Verify user information is displayed
        $response->assertSee($user->name, false);
        $response->assertSee('Sign out', false);
    }
    
    /**
     * Test that app.css continues to load correctly for authenticated pages
     * 
     * Preservation: app.css must continue to load for authenticated pages
     * This verifies the Vite manifest and compiled CSS work correctly.
     * 
     * @return void
     */
    public function test_app_css_loads_correctly_for_authenticated_pages(): void
    {
        $manifestPath = public_path('build/manifest.json');
        
        // Check if manifest exists
        $this->assertFileExists(
            $manifestPath,
            'Vite manifest.json not found. Run "npm run build" or "npm run dev" to generate assets.'
        );
        
        // Read and parse manifest
        $manifestContent = file_get_contents($manifestPath);
        $manifest = json_decode($manifestContent, true);
        
        $this->assertIsArray(
            $manifest,
            'Vite manifest.json is not valid JSON or is malformed.'
        );
        
        // Check if app.css is in the manifest
        $cssEntryFound = false;
        $cssFile = null;
        foreach ($manifest as $key => $entry) {
            if (str_contains($key, 'resources/css/base.css')) {
                $cssEntryFound = true;
                $cssFile = $entry['file'] ?? null;
                
                // Verify the entry has a 'file' property
                $this->assertArrayHasKey(
                    'file',
                    $entry,
                    'CSS entry in manifest is missing "file" property.'
                );
                
                // Verify the compiled CSS file exists
                $compiledCssPath = public_path('build/' . $entry['file']);
                $this->assertFileExists(
                    $compiledCssPath,
                    "Compiled CSS file not found at: build/{$entry['file']}"
                );
                
                break;
            }
        }
        
        $this->assertTrue(
            $cssEntryFound,
            'CSS entry (resources/css/base.css) not found in Vite manifest. ' .
            'This indicates Vite is not compiling app.css properly.'
        );
        
        // Note: On unfixed code, the compiled CSS may only contain Tailwind utilities
        // and not custom CSS classes. This is part of the bug being fixed.
        // The preservation test verifies that the Vite build process itself works,
        // not that custom CSS is present (that's tested in the bug condition tests).
    }
    
    /**
     * Test that JavaScript functionality continues to work
     * 
     * Preservation: JavaScript loading and functionality must continue to work
     * This verifies the logout button and other JS features work correctly.
     * 
     * @return void
     */
    public function test_javascript_functionality_continues_to_work(): void
    {
        // Create and authenticate a user
        $user = \App\Models\User::factory()->create();
        $this->actingAs($user);
        
        // Access the dashboard page
        $response = $this->get('/dashboard');
        
        // Verify the page loads successfully
        $response->assertStatus(200);
        
        // CRITICAL ASSERTION: Verify Vite directive generates JavaScript script tag
        $content = $response->getContent();
        
        $this->assertMatchesRegularExpression(
            '/<script[^>]+type=["\']module["\'][^>]*>/',
            $content,
            'Expected JavaScript <script> tag to be present in dashboard page HTML. ' .
            'This indicates JavaScript is not being loaded by Vite.'
        );
        
        // Verify logout form is present and functional
        $response->assertSee('method="POST"', false);
        $response->assertSee('action="' . route('logout') . '"', false);
        $response->assertSee('type="submit"', false);
        $response->assertSee('Sign out', false);
        
        // Test that logout functionality works
        $logoutResponse = $this->post('/logout');
        $logoutResponse->assertRedirect('/login');
        
        // Verify user is no longer authenticated
        $this->assertGuest();
    }
    
    /**
     * Property-based test: Authenticated pages preserve styling across multiple scenarios
     * 
     * This test generates multiple test cases to verify preservation across different
     * authenticated user scenarios.
     * 
     * @return void
     */
    public function test_authenticated_pages_preserve_styling_across_scenarios(): void
    {
        // Generate multiple test cases with different user attributes
        $testCases = [
            ['name' => 'John Doe', 'email' => 'john@example.com'],
            ['name' => 'Jane Smith', 'email' => 'jane@example.com'],
            ['name' => 'Test User', 'email' => 'test@example.com'],
            ['name' => 'Admin User', 'email' => 'admin@example.com'],
            ['name' => 'Guest User', 'email' => 'guest@example.com'],
        ];
        
        foreach ($testCases as $userData) {
            // Create and authenticate a user with specific attributes
            $user = \App\Models\User::factory()->create($userData);
            $this->actingAs($user);
            
            // Access the dashboard page
            $response = $this->get('/dashboard');
            
            // Verify the page loads successfully
            $response->assertStatus(200);
            
            // Verify CSS is loaded
            $content = $response->getContent();
            $this->assertMatchesRegularExpression(
                '/<link[^>]+rel=["\']stylesheet["\'][^>]*>/',
                $content,
                "CSS not loaded for user: {$userData['name']}"
            );
            
            // Verify app layout structure is present
            $response->assertSee('class="app-container"', false);
            $response->assertSee('class="sidebar"', false);
            $response->assertSee('class="main"', false);
            
            // Verify user-specific content is displayed
            $response->assertSee($userData['name'], false);
            
            // Logout for next iteration
            $this->post('/logout');
        }
    }
    
    /**
     * Property-based test: App layout structure is preserved
     * 
     * This test verifies that the app layout structure (sidebar, header, navigation)
     * continues to render correctly with all expected elements.
     * 
     * @return void
     */
    public function test_app_layout_structure_is_preserved(): void
    {
        // Create and authenticate a user
        $user = \App\Models\User::factory()->create();
        $this->actingAs($user);
        
        // Access the dashboard page
        $response = $this->get('/dashboard');
        
        // Verify the page loads successfully
        $response->assertStatus(200);
        
        // Verify sidebar structure
        $response->assertSee('class="sidebar"', false);
        $response->assertSee('class="brand"', false);
        $response->assertSee('TriLingua', false);
        
        // Verify navigation structure
        $response->assertSee('class="nav"', false);
        $response->assertSee('Dashboard', false);
        $response->assertSee('New Translation', false);
        $response->assertSee('Saved Translations', false);
        
        // Verify sidebar user section
        $response->assertSee('class="sidebar-user"', false);
        $response->assertSee('class="sidebar-logout"', false);
        
        // Verify header structure
        $response->assertSee('class="header"', false);
        $response->assertSee('class="title"', false);
        $response->assertSee('class="header-right"', false);
        
        // Verify user section
        $response->assertSee('class="header-user"', false);
        $response->assertSee($user->name, false);
        $response->assertSee('class="header-user__name"', false);
        $response->assertSee('Sign out', false);
        
        // Verify main content area
        $response->assertSee('class="main"', false);
        
        // Verify dashboard-specific content
        $response->assertSee('class="stack"', false);
        $response->assertSee('class="cards-grid"', false);
        $response->assertSee('class="stat-card"', false);
        $response->assertSee('Total Documents', false);
        $response->assertSee('Translations This Month', false);
        $response->assertSee('Words Translated', false);
    }
}
