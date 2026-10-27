# Implementation Plan: Per-View CSS Architecture

## Overview

This plan migrates the Laravel application from a two-file CSS architecture (app.css and guest.css) to a per-view CSS structure. The implementation creates dedicated CSS files for each view, extracts shared styles into base.css, organizes layout-specific styles, updates Vite configuration for multiple entry points, and modifies Blade templates to reference the new CSS files. All changes must maintain zero visual regression.

## Tasks

- [x] 1. Create new CSS directory structure and base styles file
  - Create resources/css/base.css with CSS variables, resets, and common utilities
  - Create resources/css/layouts/ directory
  - Create resources/css/views/ directory
  - Create resources/css/views/auth/ directory
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4_

- [ ] 2. Extract and migrate base styles from existing CSS files
  - [x] 2.1 Extract CSS custom properties from app.css and guest.css to base.css
    - Merge :root variables from both files (--bg, --card-bg, --muted, --text, --accent, --primary, --border, --radius, --sidebar-width)
    - Ensure no duplicate or conflicting variable definitions
    - _Requirements: 2.2, 3.4_

  - [x] 2.2 Extract global element styles to base.css
    - Move universal selector, html, and body styles from both files
    - Include box-sizing, height, margin, font-family, background, color rules
    - _Requirements: 2.3, 3.4_

  - [x] 2.3 Extract common utility classes to base.css
    - Move shared utilities: .hidden, .text-sm, .mb-1, .mb-2, .mb-4, .mt-2, .w-full
    - Move common form styles: .form-field, .error-message
    - Move common button base styles if shared across views
    - _Requirements: 2.4, 3.4_

  - [x] 2.4 Write unit tests for base.css content
    - Test that base.css contains all required CSS custom properties
    - Test that base.css contains global element styles
    - Test that base.css contains common utility classes
    - _Requirements: 2.2, 2.3, 2.4_

- [ ] 3. Create layout CSS files and migrate layout-specific styles
  - [x] 3.1 Create resources/css/layouts/guest.css with authentication layout styles
    - Move .auth-body, .auth-container, .auth-card from guest.css
    - Move .auth-logo, .auth-header, .auth-subtitle styles
    - Move .divider-text and related pseudo-elements
    - _Requirements: 7.1, 7.4, 3.1, 3.4_

  - [x] 3.2 Create resources/css/layouts/app.css with authenticated layout styles
    - Move .app-container, .sidebar, .brand, .nav, .nav-link styles from app.css
    - Move .storage, .progress styles
    - Move .main, .header layout styles
    - _Requirements: 7.2, 7.4, 3.2, 3.4_

  - [x] 3.3 Write unit tests for layout CSS files
    - Test that layouts/guest.css contains auth layout selectors
    - Test that layouts/app.css contains sidebar and navigation selectors
    - _Requirements: 7.1, 7.2_

- [ ] 4. Create view-specific CSS files and migrate view styles
  - [x] 4.1 Create resources/css/views/auth/login.css
    - Move login-specific form styles from guest.css
    - Include .auth-form, .btn-auth, .auth-forgot, .link-underline
    - Include .social-buttons, .btn-social, .auth-footer, .link-bold
    - _Requirements: 1.1, 3.1, 3.5_

  - [x] 4.2 Create resources/css/views/auth/register.css
    - Copy shared authentication form styles from login.css
    - Add any register-specific styles if they exist
    - _Requirements: 1.2, 3.1, 3.5_

  - [x] 4.3 Create resources/css/views/dashboard.css
    - Move dashboard-specific styles from app.css
    - Include .cards-grid, .stat-card, .table-card, .card-title
    - Include .table and related table styles
    - Include .text-success, .text-warning status indicators
    - _Requirements: 1.3, 3.2, 3.5_

  - [x] 4.4 Create resources/css/views/welcome.css
    - Move welcome page styles from app.css
    - Include .hero, .left-hero, .hero-right if they exist
    - Include .features, .feature-item if they exist
    - Include .illustration and welcome-specific styles
    - _Requirements: 1.4, 3.3, 3.5_

  - [x] 4.5 Write unit tests for view-specific CSS files
    - Test that each view CSS file exists at expected path
    - Test that view CSS files contain expected selectors
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 5. Checkpoint - Verify CSS file structure and content
  - Ensure all CSS files are created with correct content, ask the user if questions arise.

- [ ] 6. Update Vite configuration for multiple CSS entry points
  - [x] 6.1 Modify vite.config.js to include all CSS modules as inputs
    - Add resources/css/base.css to input array
    - Add resources/css/layouts/app.css to input array
    - Add resources/css/layouts/guest.css to input array
    - Add resources/css/views/auth/login.css to input array
    - Add resources/css/views/auth/register.css to input array
    - Add resources/css/views/dashboard.css to input array
    - Add resources/css/views/welcome.css to input array
    - Maintain existing resources/js/app.js entry
    - _Requirements: 4.1, 4.2, 4.5_

  - [x] 6.2 Write unit tests for Vite configuration
    - Test that vite.config.js contains all CSS module entries
    - Test that JavaScript entry points are maintained
    - _Requirements: 4.1, 4.5_

- [ ] 7. Update Blade templates to reference new CSS files
  - [x] 7.1 Update resources/views/layouts/guest.blade.php
    - Add @vite directive to load base.css and layouts/guest.css
    - Add @yield('styles') section for view-specific CSS
    - _Requirements: 7.3, 5.1, 5.2_

  - [x] 7.2 Update resources/views/layouts/app.blade.php
    - Add @vite directive to load base.css and layouts/app.css
    - Add @yield('styles') section for view-specific CSS
    - _Requirements: 7.3, 5.3, 5.4_

  - [x] 7.3 Update resources/views/auth/login.blade.php
    - Add @section('styles') with @vite directive for views/auth/login.css
    - Verify view extends guest layout
    - _Requirements: 5.1, 5.5_

  - [x] 7.4 Update resources/views/auth/register.blade.php
    - Add @section('styles') with @vite directive for views/auth/register.css
    - Verify view extends guest layout
    - _Requirements: 5.2, 5.5_

  - [x] 7.5 Update resources/views/dashboard.blade.php
    - Add @section('styles') with @vite directive for views/dashboard.css
    - Verify view extends app layout
    - _Requirements: 5.3, 5.5_

  - [x] 7.6 Update resources/views/welcome.blade.php
    - Add @vite directive or @section('styles') for views/welcome.css
    - Handle welcome page layout appropriately
    - _Requirements: 5.4, 5.5_

  - [x] 7.7 Write unit tests for Blade template CSS references
    - Test that login view loads base.css and login.css
    - Test that register view loads base.css and register.css
    - Test that dashboard view loads base.css and dashboard.css
    - Test that welcome view loads base.css and welcome.css
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 8. Build assets and verify build output
  - [ ] 8.1 Run npm run build to generate production assets
    - Execute build command
    - Verify build completes without errors
    - _Requirements: 4.3, 10.1, 10.2_

  - [ ] 8.2 Verify manifest.json contains all CSS modules
    - Check that public/build/manifest.json exists
    - Verify manifest contains entries for base.css
    - Verify manifest contains entries for layout CSS files
    - Verify manifest contains entries for view CSS files
    - Verify all entries have hashed filenames
    - _Requirements: 10.1, 10.2, 10.4_

  - [ ] 8.3 Verify separate CSS files exist in public/build
    - Check that hashed CSS files exist for each module
    - Verify files contain minified CSS content
    - _Requirements: 10.3, 10.5_

  - [ ] 8.4 Write unit tests for build output verification
    - Test that manifest.json exists after build
    - Test that manifest contains all CSS module entries
    - Test that separate CSS files exist for each module
    - _Requirements: 10.1, 10.2, 10.3_

- [ ] 9. Checkpoint - Verify build output and template loading
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Test Tailwind CSS integration with new architecture
  - [ ] 10.1 Verify Tailwind directives work in all CSS modules
    - Check that Tailwind utilities are generated in built CSS
    - Verify @tailwind directives are processed correctly
    - _Requirements: 6.1, 6.2_

  - [ ] 10.2 Verify Tailwind configuration scans all templates
    - Confirm tailwind.config.js content paths are unchanged
    - Test that utility classes from templates appear in built CSS
    - _Requirements: 6.3_

  - [ ] 10.3 Write property test for Tailwind integration preservation
    - **Property 4: Tailwind Integration Preservation**
    - **Validates: Requirements 6.1, 6.2, 6.4**
    - Test that CSS modules with Tailwind directives generate utility classes
    - Test that production builds purge unused classes while maintaining referenced classes
    - Run 100+ iterations with random Tailwind utility classes
    - _Requirements: 6.1, 6.2, 6.4_

- [ ] 11. Verify hot module replacement in development mode
  - [ ] 11.1 Start development server and test HMR for CSS modules
    - Modify a CSS module and verify browser updates without reload
    - Test HMR for base.css, layout CSS, and view CSS files
    - _Requirements: 4.4_

  - [ ] 11.2 Write property test for HMR functionality
    - **Property 6: Hot Module Replacement Functionality**
    - **Validates: Requirements 4.4**
    - Test that modifying any CSS module triggers HMR update
    - Run 100+ iterations across different CSS modules
    - _Requirements: 4.4_

- [ ] 12. Remove legacy CSS files and references
  - [ ] 12.1 Delete resources/css/app.css
    - Remove the file after confirming all styles are migrated
    - _Requirements: 8.1_

  - [ ] 12.2 Delete resources/css/guest.css
    - Remove the file after confirming all styles are migrated
    - _Requirements: 8.2_

  - [ ] 12.3 Verify no references to legacy CSS files remain
    - Search codebase for references to app.css and guest.css
    - Remove any remaining references
    - _Requirements: 8.3, 8.4, 8.5_

  - [ ] 12.4 Write unit tests for legacy file removal
    - Test that app.css does not exist
    - Test that guest.css does not exist
    - Test that vite.config.js does not reference legacy files
    - _Requirements: 8.1, 8.2, 8.3_

- [ ] 13. Run comprehensive property-based tests
  - [ ] 13.1 Write property test for CSS cascade consistency
    - **Property 1: CSS Cascade Consistency**
    - **Validates: Requirements 2.5, 7.5**
    - Test that modifying base or layout CSS affects all views that import it
    - Run 100+ iterations with random CSS rules
    - _Requirements: 2.5, 7.5_

  - [ ] 13.2 Write property test for view CSS isolation
    - **Property 2: View CSS Isolation**
    - **Validates: Requirements 5.5, 7.3**
    - Test that each view loads only its own CSS module and not others
    - Run 100+ iterations across all views
    - _Requirements: 5.5, 7.3_

  - [ ] 13.3 Write property test for build output completeness
    - **Property 3: Build Output Completeness**
    - **Validates: Requirements 4.3, 10.2, 10.5**
    - Test that each CSS module in config generates hashed, minified output
    - Run 100+ iterations
    - _Requirements: 4.3, 10.2, 10.5_

  - [ ] 13.4 Write property test for visual regression prevention
    - **Property 5: Visual Regression Prevention**
    - **Validates: Requirements 3.5, 8.5**
    - Test that visual appearance is identical before and after migration
    - Run 100+ iterations across all views with screenshot comparison
    - _Requirements: 3.5, 8.5_

  - [ ] 13.5 Write property test for manifest asset resolution
    - **Property 7: Manifest Asset Resolution**
    - **Validates: Requirements 10.4**
    - Test that views in production load CSS files using hashed filenames from manifest
    - Run 100+ iterations
    - _Requirements: 10.4_

- [ ] 14. Create documentation for new CSS architecture
  - [ ] 14.1 Create CSS_ARCHITECTURE.md documentation file
    - Document the directory structure for CSS modules
    - Provide examples of creating CSS modules for new views
    - Describe when to add styles to base vs view-specific files
    - Include instructions for updating Vite configuration
    - Explain how to reference CSS modules in Blade templates
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ] 14.2 Write unit tests for documentation
    - Test that CSS_ARCHITECTURE.md exists
    - Test that documentation contains required sections
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 15. Final checkpoint - Run all tests and verify migration
  - Ensure all tests pass, verify zero visual regression, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- Property tests validate universal correctness properties with 100+ iterations each
- Unit tests validate specific examples and edge cases
- All changes must maintain zero visual regression
- The migration preserves existing Tailwind CSS integration
- Hot module replacement must work in development mode for all CSS modules
