<?php

namespace Tests\Unit;

use PHPUnit\Framework\TestCase;

class BaseCssContentTest extends TestCase
{
    private string $baseCssPath;
    private string $baseCssContent;

    protected function setUp(): void
    {
        parent::setUp();
        // Calculate base path relative to the test file location
        $this->baseCssPath = dirname(__DIR__, 2) . '/resources/css/base.css';
        
        if (!file_exists($this->baseCssPath)) {
            $this->fail("base.css file does not exist at {$this->baseCssPath}");
        }
        
        $this->baseCssContent = file_get_contents($this->baseCssPath);
    }

    /**
     * Test that base.css contains all required CSS custom properties
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_contains_all_required_css_custom_properties(): void
    {
        // Required CSS custom properties from requirements 2.2
        $requiredProperties = [
            '--bg',
            '--card-bg',
            '--muted',
            '--text',
            '--accent',
            '--primary',
            '--border',
            '--radius',
            '--sidebar-width',
        ];

        foreach ($requiredProperties as $property) {
            $this->assertStringContainsString(
                $property . ':',
                $this->baseCssContent,
                "base.css should contain CSS custom property: {$property}"
            );
        }
    }

    /**
     * Test that base.css contains CSS custom properties within :root selector
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_contains_root_selector_with_custom_properties(): void
    {
        // Verify :root selector exists
        $this->assertStringContainsString(
            ':root',
            $this->baseCssContent,
            'base.css should contain :root selector for CSS custom properties'
        );

        // Verify :root block contains custom properties
        preg_match('/:root\s*\{([^}]+)\}/s', $this->baseCssContent, $matches);
        
        $this->assertNotEmpty(
            $matches,
            ':root selector should contain CSS custom properties'
        );

        if (isset($matches[1])) {
            $rootContent = $matches[1];
            $this->assertStringContainsString('--', $rootContent, ':root should contain CSS variables');
        }
    }

    /**
     * Test that base.css contains global element styles
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_contains_global_element_styles(): void
    {
        // Required global element selectors from requirements 2.3
        $requiredSelectors = [
            '*',           // Universal selector
            'html',        // HTML element
            'body',        // Body element
        ];

        foreach ($requiredSelectors as $selector) {
            // Use regex to match selector followed by optional whitespace and opening brace
            $pattern = '/' . preg_quote($selector, '/') . '\s*[,{]/';
            
            $this->assertMatchesRegularExpression(
                $pattern,
                $this->baseCssContent,
                "base.css should contain global element style for: {$selector}"
            );
        }
    }

    /**
     * Test that base.css contains box-sizing rule in universal selector
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_contains_box_sizing_rule(): void
    {
        $this->assertStringContainsString(
            'box-sizing',
            $this->baseCssContent,
            'base.css should contain box-sizing rule'
        );
    }

    /**
     * Test that base.css contains html and body height rules
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_contains_html_body_height_rules(): void
    {
        // Check for height: 100% in html/body context
        preg_match('/html[^{]*\{[^}]*height[^}]*\}/s', $this->baseCssContent, $htmlMatches);
        preg_match('/body[^{]*\{[^}]*height[^}]*\}/s', $this->baseCssContent, $bodyMatches);
        
        $this->assertTrue(
            !empty($htmlMatches) || !empty($bodyMatches),
            'base.css should contain height rules for html or body elements'
        );
    }

    /**
     * Test that base.css contains body font-family rule
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_contains_body_font_family(): void
    {
        $this->assertStringContainsString(
            'font-family',
            $this->baseCssContent,
            'base.css should contain font-family rule'
        );
    }

    /**
     * Test that base.css contains common utility classes
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_contains_common_utility_classes(): void
    {
        // Required utility classes from requirements 2.4
        $requiredUtilityClasses = [
            '.hidden',
            '.text-sm',
            '.mb-1',
            '.mb-2',
            '.mb-4',
            '.mt-2',
            '.w-full',
            '.muted',
            '.center',
        ];

        foreach ($requiredUtilityClasses as $class) {
            // Use regex to match class selector followed by optional whitespace and opening brace
            $pattern = '/' . preg_quote($class, '/') . '\s*[,{]/';
            
            $this->assertMatchesRegularExpression(
                $pattern,
                $this->baseCssContent,
                "base.css should contain common utility class: {$class}"
            );
        }
    }

    /**
     * Test that base.css contains common component styles
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_contains_common_component_styles(): void
    {
        // Common component classes that should be in base.css
        $requiredComponentClasses = [
            '.btn',
            '.card',
            '.form-field',
            '.error-message',
            '.link',
        ];

        foreach ($requiredComponentClasses as $class) {
            $pattern = '/' . preg_quote($class, '/') . '\s*[,{]/';
            
            $this->assertMatchesRegularExpression(
                $pattern,
                $this->baseCssContent,
                "base.css should contain common component class: {$class}"
            );
        }
    }

    /**
     * Test that base.css contains button variant classes
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_contains_button_variant_classes(): void
    {
        $buttonVariants = [
            '.btn.secondary',
            '.btn.primary',
            '.btn.block',
        ];

        foreach ($buttonVariants as $variant) {
            $this->assertStringContainsString(
                $variant,
                $this->baseCssContent,
                "base.css should contain button variant: {$variant}"
            );
        }
    }

    /**
     * Test that base.css contains form field styles
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_contains_form_field_styles(): void
    {
        // Form field related selectors
        $formSelectors = [
            '.form-field label',
            '.form-field input',
        ];

        foreach ($formSelectors as $selector) {
            $this->assertStringContainsString(
                $selector,
                $this->baseCssContent,
                "base.css should contain form selector: {$selector}"
            );
        }
    }

    /**
     * Test that base.css contains divider utility
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_contains_divider_utility(): void
    {
        $this->assertStringContainsString(
            '.divider',
            $this->baseCssContent,
            'base.css should contain .divider utility class'
        );
    }

    /**
     * Test that base.css file is not empty
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_is_not_empty(): void
    {
        $this->assertNotEmpty(
            trim($this->baseCssContent),
            'base.css should not be empty'
        );
    }

    /**
     * Test that base.css contains valid CSS syntax (basic check)
     */
    #[\PHPUnit\Framework\Attributes\Test]
    #[\PHPUnit\Framework\Attributes\Group('per-view-css-architecture')]
    #[\PHPUnit\Framework\Attributes\Group('base-css')]
    public function test_base_css_has_balanced_braces(): void
    {
        $openBraces = substr_count($this->baseCssContent, '{');
        $closeBraces = substr_count($this->baseCssContent, '}');
        
        $this->assertEquals(
            $openBraces,
            $closeBraces,
            'base.css should have balanced opening and closing braces'
        );
    }
}
