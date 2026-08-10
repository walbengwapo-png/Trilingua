<?php

namespace Tests\Unit;

use PHPUnit\Framework\TestCase;

class LayoutCssContentTest extends TestCase
{
    private string $guestCssPath;
    private string $guestCssContent;
    private string $appCssPath;
    private string $appCssContent;

    protected function setUp(): void
    {
        parent::setUp();
        
        // Calculate paths relative to the test file location
        $basePath = dirname(__DIR__, 2);
        $this->guestCssPath = $basePath . '/resources/css/layouts/guest.css';
        $this->appCssPath = $basePath . '/resources/css/layouts/app.css';
        
        // Verify guest.css exists
        if (!file_exists($this->guestCssPath)) {
            $this->fail("guest.css file does not exist at {$this->guestCssPath}");
        }
        
        // Verify app.css exists
        if (!file_exists($this->appCssPath)) {
            $this->fail("app.css file does not exist at {$this->appCssPath}");
        }
        
        $this->guestCssContent = file_get_contents($this->guestCssPath);
        $this->appCssContent = file_get_contents($this->appCssPath);
    }

    /**
     * Test that layouts/guest.css contains auth layout selectors
     * 
     * **Validates: Requirements 7.1**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_guest_css_contains_auth_layout_selectors(): void
    {
        // Required auth layout selectors from requirements 7.1
        $requiredSelectors = [
            '.auth-body',
            '.auth-container',
            '.auth-card',
        ];

        foreach ($requiredSelectors as $selector) {
            // Use regex to match selector followed by optional whitespace and opening brace
            $pattern = '/' . preg_quote($selector, '/') . '\s*[,{]/';
            
            $this->assertMatchesRegularExpression(
                $pattern,
                $this->guestCssContent,
                "layouts/guest.css should contain auth layout selector: {$selector}"
            );
        }
    }

    /**
     * Test that layouts/guest.css contains auth logo selector
     * 
     * **Validates: Requirements 7.1**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_guest_css_contains_auth_logo_selector(): void
    {
        $this->assertStringContainsString(
            '.auth-brand__logo',
            $this->guestCssContent,
            'layouts/guest.css should contain .auth-brand__logo selector'
        );
    }

    /**
     * Test that layouts/guest.css contains auth header selector
     * 
     * **Validates: Requirements 7.1**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_guest_css_contains_auth_header_selector(): void
    {
        $this->assertStringContainsString(
            '.auth-header',
            $this->guestCssContent,
            'layouts/guest.css should contain .auth-header selector'
        );
    }

    /**
     * Test that layouts/guest.css contains divider text selector
     * 
     * **Validates: Requirements 7.1**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_guest_css_contains_divider_text_selector(): void
    {
        $this->assertStringContainsString(
            '.divider-text',
            $this->guestCssContent,
            'layouts/guest.css should contain .divider-text selector'
        );
    }

    /**
     * Test that layouts/app.css contains sidebar selector
     * 
     * **Validates: Requirements 7.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_app_css_contains_sidebar_selector(): void
    {
        $pattern = '/\.sidebar\s*[,{]/';
        
        $this->assertMatchesRegularExpression(
            $pattern,
            $this->appCssContent,
            'layouts/app.css should contain .sidebar selector'
        );
    }

    /**
     * Test that layouts/app.css contains navigation selectors
     * 
     * **Validates: Requirements 7.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_app_css_contains_navigation_selectors(): void
    {
        // Required navigation selectors from requirements 7.2
        $requiredSelectors = [
            '.nav',
            '.nav-link',
        ];

        foreach ($requiredSelectors as $selector) {
            $this->assertStringContainsString(
                $selector,
                $this->appCssContent,
                "layouts/app.css should contain navigation selector: {$selector}"
            );
        }
    }

    /**
     * Test that layouts/app.css contains app container selector
     * 
     * **Validates: Requirements 7.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_app_css_contains_app_container_selector(): void
    {
        $pattern = '/\.app-container\s*[,{]/';
        
        $this->assertMatchesRegularExpression(
            $pattern,
            $this->appCssContent,
            'layouts/app.css should contain .app-container selector'
        );
    }

    /**
     * Test that layouts/app.css contains main content area selector
     * 
     * **Validates: Requirements 7.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_app_css_contains_main_selector(): void
    {
        $pattern = '/\.main\s*[,{]/';
        
        $this->assertMatchesRegularExpression(
            $pattern,
            $this->appCssContent,
            'layouts/app.css should contain .main selector for main content area'
        );
    }

    /**
     * Test that layouts/app.css contains header selector
     * 
     * **Validates: Requirements 7.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_app_css_contains_header_selector(): void
    {
        $pattern = '/\.header\s*[,{]/';
        
        $this->assertMatchesRegularExpression(
            $pattern,
            $this->appCssContent,
            'layouts/app.css should contain .header selector'
        );
    }

    /**
     * Test that layouts/app.css contains brand selector
     * 
     * **Validates: Requirements 7.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_app_css_contains_brand_selector(): void
    {
        $this->assertStringContainsString(
            '.brand',
            $this->appCssContent,
            'layouts/app.css should contain .brand selector'
        );
    }

    /**
     * Test that layouts/guest.css is not empty
     * 
     * **Validates: Requirements 7.1**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_guest_css_is_not_empty(): void
    {
        $this->assertNotEmpty(
            trim($this->guestCssContent),
            'layouts/guest.css should not be empty'
        );
    }

    /**
     * Test that layouts/app.css is not empty
     * 
     * **Validates: Requirements 7.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_app_css_is_not_empty(): void
    {
        $this->assertNotEmpty(
            trim($this->appCssContent),
            'layouts/app.css should not be empty'
        );
    }

    /**
     * Test that layouts/guest.css has balanced braces
     * 
     * **Validates: Requirements 7.1**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_guest_css_has_balanced_braces(): void
    {
        $openBraces = substr_count($this->guestCssContent, '{');
        $closeBraces = substr_count($this->guestCssContent, '}');
        
        $this->assertEquals(
            $openBraces,
            $closeBraces,
            'layouts/guest.css should have balanced opening and closing braces'
        );
    }

    /**
     * Test that layouts/app.css has balanced braces
     * 
     * **Validates: Requirements 7.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_app_css_has_balanced_braces(): void
    {
        $openBraces = substr_count($this->appCssContent, '{');
        $closeBraces = substr_count($this->appCssContent, '}');
        
        $this->assertEquals(
            $openBraces,
            $closeBraces,
            'layouts/app.css should have balanced opening and closing braces'
        );
    }

    /**
     * Test that layouts/guest.css contains responsive media query
     * 
     * **Validates: Requirements 7.1**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_guest_css_contains_responsive_media_query(): void
    {
        $this->assertStringContainsString(
            '@media',
            $this->guestCssContent,
            'layouts/guest.css should contain responsive media query'
        );
    }

    /**
     * Test that layouts/app.css contains sidebar user selector
     * 
     * **Validates: Requirements 7.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_app_css_contains_storage_selector(): void
    {
        $this->assertStringContainsString(
            '.sidebar-user',
            $this->appCssContent,
            'layouts/app.css should contain .sidebar-user selector'
        );
    }

    /**
     * Test that layouts/app.css contains header right selector
     * 
     * **Validates: Requirements 7.2**
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('layout-css')]
    public function test_app_css_contains_progress_selector(): void
    {
        $this->assertStringContainsString(
            '.header-right',
            $this->appCssContent,
            'layouts/app.css should contain .header-right selector'
        );
    }
}
