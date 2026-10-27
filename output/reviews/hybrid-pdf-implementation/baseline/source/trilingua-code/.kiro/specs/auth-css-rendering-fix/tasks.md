# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Authentication Pages CSS Not Rendering
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to concrete failing cases: login and register pages accessed via guest layout
  - Test that accessing /login and /register routes results in CSS styles being rendered (from Bug Condition in design)
  - The test assertions should match the Expected Behavior Properties from design: CSS files load successfully, visual elements are styled correctly
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found: CSS not loading, 404 errors, missing Vite manifest entries, unstyled HTML
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Authenticated Pages Continue Working
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for authenticated pages (dashboard, app layout)
  - Write property-based tests capturing observed behavior patterns from Preservation Requirements
  - Test that dashboard page renders with proper styling (sidebar, header, navigation)
  - Test that app.css continues to load correctly for authenticated pages
  - Test that JavaScript functionality continues to work (logout button, etc.)
  - Property-based testing generates many test cases for stronger guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix for authentication pages CSS rendering

  - [x] 3.1 Create guest.css with guest-specific styles
    - Create new file: resources/css/guest.css
    - Extract guest-specific styles from app.css: .guest-center, .hero, .left-hero, .form-card, .metrics, .metric, .metric-title, .metric-value
    - Include base styles: CSS variables (:root), reset styles, body/html base styles
    - Include shared utilities: .btn, .form-field, .form-area, .actions-grid, .divider, .link, .error-message, .subtitle, .muted, .center
    - Do NOT include app-specific styles: .app-container, .sidebar, .main, .header, .nav
    - _Bug_Condition: isBugCondition(input) where input.route IN ['login', 'register'] AND input.layout == 'guest.blade.php'_
    - _Expected_Behavior: cssStylesRendered(response) AND visualElementsDisplayCorrectly(response)_
    - _Preservation: Dashboard and authenticated pages must continue to render with proper styling_
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 3.2 Modify app.css to remove guest-specific styles
    - Remove guest-specific styles: .guest-center, .hero, .left-hero, .form-card, .metrics, .metric, .metric-title, .metric-value
    - Keep app-specific styles: .app-container, .sidebar, .main, .header, .nav, .storage, .progress
    - Keep shared styles: CSS variables, base styles, form helpers, button styles
    - Ensure no duplicate styles between app.css and guest.css (except shared utilities)
    - _Bug_Condition: isBugCondition(input) where input.route IN ['login', 'register']_
    - _Expected_Behavior: Authentication pages load guest.css, authenticated pages load app.css_
    - _Preservation: Authenticated pages must continue to use app.css without regression_
    - _Requirements: 2.3, 2.5, 3.1_

  - [x] 3.3 Update Vite configuration to include guest.css
    - Modify vite.config.js
    - Update input array from ['resources/css/app.css', 'resources/js/app.js'] to ['resources/css/app.css', 'resources/css/guest.css', 'resources/js/app.js']
    - Verify laravel and tailwindcss plugins are correctly configured
    - Maintain refresh: true setting for HMR
    - _Bug_Condition: Vite must compile both CSS files for proper asset loading_
    - _Expected_Behavior: Vite compiles guest.css and includes it in manifest.json_
    - _Preservation: Existing Vite build process for app.css and JavaScript must continue working_
    - _Requirements: 2.4, 3.4_

  - [x] 3.4 Update guest.blade.php to load guest.css
    - Modify resources/views/layouts/guest.blade.php
    - Change @vite directive from @vite(['resources/css/app.css', 'resources/js/app.js']) to @vite(['resources/css/guest.css', 'resources/js/app.js'])
    - _Bug_Condition: Guest layout must load guest.css instead of app.css_
    - _Expected_Behavior: Authentication pages load and apply guest.css styles_
    - _Preservation: App layout continues to load app.css unchanged_
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 3.5 Verify app.blade.php continues to load app.css
    - Inspect resources/views/layouts/app.blade.php
    - Confirm @vite directive remains @vite(['resources/css/app.css', 'resources/js/app.js'])
    - No changes should be needed to this file
    - _Preservation: Authenticated pages must continue loading app.css_
    - _Requirements: 3.1, 3.3_

  - [x] 3.6 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Authentication Pages CSS Rendering
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - Access /login and /register routes
    - Verify CSS files load successfully (200 status in network tab)
    - Verify visual elements are styled correctly (colors, layout, buttons, forms)
    - Verify Vite manifest includes guest.css
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.7 Verify preservation tests still pass
    - **Property 2: Preservation** - Authenticated Pages Continue Working
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - Access /dashboard and verify styling is identical to before fix
    - Verify sidebar, header, navigation render correctly
    - Verify JavaScript functionality works (logout button, etc.)
    - Verify app.css loads successfully for authenticated pages
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run all exploration and preservation tests
  - Verify login page renders with proper CSS styling
  - Verify register page renders with proper CSS styling
  - Verify dashboard page continues to render with proper CSS styling
  - Verify no visual regressions on any page
  - Verify Vite build process works correctly (npm run build)
  - Ensure all tests pass, ask the user if questions arise
