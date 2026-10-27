# Design Document: Per-View CSS Architecture

## Overview

This design describes the migration from a two-file CSS architecture (app.css and guest.css) to a per-view CSS file structure for a Laravel application. The new architecture organizes CSS files by view, with shared styles extracted into a base file and layout-specific styles in dedicated layout files.

### Goals

- Improve CSS maintainability by colocating styles with their corresponding views
- Reduce CSS bloat by loading only the styles needed for each page
- Maintain clear separation between base styles, layout styles, and view-specific styles
- Preserve existing Tailwind CSS integration and build tooling
- Ensure zero visual regression during migration

### Non-Goals

- Refactoring existing CSS class names or design system
- Implementing CSS modules or CSS-in-JS solutions
- Changing the underlying Tailwind CSS configuration
- Modifying the visual design of any views

## Architecture

### Directory Structure

```
resources/css/
├── base.css                    # Common styles, variables, utilities
├── layouts/
│   ├── app.css                # Authenticated layout styles
│   └── guest.css              # Guest layout styles
└── views/
    ├── auth/
    │   ├── login.css          # Login page styles
    │   └── register.css       # Register page styles
    ├── dashboard.css          # Dashboard page styles
    └── welcome.css            # Welcome page styles
```

### CSS Loading Strategy

Each view will load CSS in this order:
1. **Base styles** - Always loaded first, contains CSS variables and common utilities
2. **Layout styles** - Loaded based on which layout the view extends
3. **View-specific styles** - Loaded last, contains styles unique to that view

This cascading approach ensures proper specificity and allows view-specific styles to override layout and base styles when needed.

### Build Configuration

Vite will be configured with multiple entry points:
- Base CSS file
- Layout CSS files (app.css, guest.css)
- View-specific CSS files (login.css, register.css, dashboard.css, welcome.css)

Each entry point will be processed through Tailwind CSS and output as a separate bundle with content-based hashing for cache busting.

## Components and Interfaces

### Base CSS Module

**Purpose**: Provides foundational styles shared across all views

**Contents**:
- CSS custom properties (`:root` variables for colors, spacing, typography)
- Global resets (`*, html, body` styles)
- Utility classes used across multiple views (`.hidden`, `.text-sm`, `.w-full`, etc.)
- Common component styles (`.btn`, `.form-field`, `.error-message`)

**Interface**: Imported via `@vite(['resources/css/base.css'])` in all layout files

### Layout CSS Modules

**Purpose**: Provide styles specific to layout structure

**App Layout CSS** (`layouts/app.css`):
- Sidebar navigation styles (`.sidebar`, `.nav`, `.nav-link`)
- Main content area layout (`.app-container`, `.main`)
- Header styles (`.header`, `.title`)
- Dashboard-specific layout utilities

**Guest Layout CSS** (`layouts/guest.css`):
- Centered authentication card layout (`.auth-body`, `.auth-container`, `.auth-card`)
- Authentication-specific layout utilities

**Interface**: Imported via `@vite()` directive in corresponding layout Blade templates

### View CSS Modules

**Purpose**: Provide styles unique to individual views

**Login CSS** (`views/auth/login.css`):
- Login form specific styles
- Login-specific button states
- Login page unique components

**Register CSS** (`views/auth/register.css`):
- Registration form specific styles
- Multi-step form indicators (if applicable)
- Register-specific components

**Dashboard CSS** (`views/dashboard.css`):
- Statistics card grid (`.cards-grid`, `.stat-card`)
- Data table styles (`.table-card`, `.table`)
- Dashboard-specific status indicators (`.text-success`, `.text-warning`)

**Welcome CSS** (`views/welcome.css`):
- Hero section layout (`.hero`, `.left-hero`, `.hero-right`)
- Feature list styles (`.features`, `.feature-item`)
- Welcome page specific illustrations and graphics

**Interface**: Imported via `@vite()` directive in corresponding view Blade templates

### Vite Configuration Interface

**Input Configuration**:
```javascript
laravel({
    input: [
        'resources/css/base.css',
        'resources/css/layouts/app.css',
        'resources/css/layouts/guest.css',
        'resources/css/views/auth/login.css',
        'resources/css/views/auth/register.css',
        'resources/css/views/dashboard.css',
        'resources/css/views/welcome.css',
        'resources/js/app.js'
    ],
    refresh: true,
})
```

**Output**: Generates hashed CSS files in `public/build/` with manifest.json mapping

### Blade Template Interface

**Layout Templates**:
```php
// layouts/app.blade.php
@vite(['resources/css/base.css', 'resources/css/layouts/app.css', 'resources/js/app.js'])

// layouts/guest.blade.php
@vite(['resources/css/base.css', 'resources/css/layouts/guest.css', 'resources/js/app.js'])
```

**View Templates** (extend layouts, add view-specific CSS):
```php
// views/auth/login.blade.php
@section('styles')
    @vite(['resources/css/views/auth/login.css'])
@endsection
```

Alternative approach: Include view CSS directly in layout's head section via conditional loading based on route.

## Data Models

### CSS Module Manifest

The Vite build process generates a manifest.json file mapping source CSS files to their hashed output files:

```json
{
  "resources/css/base.css": {
    "file": "assets/base-[hash].css",
    "src": "resources/css/base.css"
  },
  "resources/css/layouts/app.css": {
    "file": "assets/app-[hash].css",
    "src": "resources/css/layouts/app.css",
    "imports": ["resources/css/base.css"]
  },
  "resources/css/views/dashboard.css": {
    "file": "assets/dashboard-[hash].css",
    "src": "resources/css/views/dashboard.css"
  }
}
```

### CSS Variable Schema

Base CSS defines a consistent variable schema used across all modules:

```css
:root {
    /* Colors */
    --bg: #f3f4f6;
    --card-bg: #ffffff;
    --muted: #6b7280;
    --text: #111827;
    --accent: #f43f5e;
    --primary: #3b82f6;
    --border: #e5e7eb;
    
    /* Spacing */
    --radius: 12px;
    --sidebar-width: 260px;
}
```

All view and layout CSS modules reference these variables for consistency.

### Style Migration Mapping

Mapping of existing styles to new CSS modules:

**From app.css**:
- CSS variables → `base.css`
- Global resets → `base.css`
- Sidebar/nav styles → `layouts/app.css`
- Dashboard-specific styles → `views/dashboard.css`
- Welcome page styles → `views/welcome.css`
- Common utilities → `base.css`

**From guest.css**:
- CSS variables → `base.css` (merged with app.css variables)
- Auth layout styles → `layouts/guest.css`
- Auth form styles → `views/auth/login.css` and `views/auth/register.css` (shared styles)
- Common utilities → `base.css`


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: CSS Cascade Consistency

*For any* CSS file in the base or layout modules, when that file is modified, all views that import it should reflect those changes in their rendered output.

**Validates: Requirements 2.5, 7.5**

### Property 2: View CSS Isolation

*For any* view in the application, when that view renders, it should load only its own view-specific CSS module and not load CSS modules belonging to other views.

**Validates: Requirements 5.5, 7.3**

### Property 3: Build Output Completeness

*For any* CSS module defined as an input in the Vite configuration, the production build should generate a corresponding output file with a content-based hash in the filename and minified CSS content.

**Validates: Requirements 4.3, 10.2, 10.5**

### Property 4: Tailwind Integration Preservation

*For any* CSS module containing Tailwind directives, the build process should generate the corresponding utility classes, and in production builds, should purge unused classes while maintaining all classes referenced in Blade templates.

**Validates: Requirements 6.1, 6.2, 6.4**

### Property 5: Visual Regression Prevention

*For any* view in the application, the visual appearance after CSS architecture migration should be identical to the appearance before migration when rendered with the same data.

**Validates: Requirements 3.5, 8.5**

### Property 6: Hot Module Replacement Functionality

*For any* CSS module in development mode, when that module's source file is modified, the browser should update the styles without a full page reload.

**Validates: Requirements 4.4**

### Property 7: Manifest Asset Resolution

*For any* view in production, when that view loads, it should load CSS files using the hashed filenames specified in the Vite manifest.json file.

**Validates: Requirements 10.4**

## Error Handling

### Build-Time Errors

**Missing CSS Files**:
- **Scenario**: A CSS module referenced in vite.config.js does not exist
- **Handling**: Vite build should fail with a clear error message indicating which CSS file is missing
- **Recovery**: Developer creates the missing CSS file or removes the reference from config

**CSS Syntax Errors**:
- **Scenario**: A CSS module contains invalid CSS syntax
- **Handling**: Vite build should fail with error message showing file and line number
- **Recovery**: Developer fixes the syntax error in the CSS file

**Circular Import Dependencies**:
- **Scenario**: CSS files import each other in a circular manner
- **Handling**: Build should detect and report circular dependency
- **Recovery**: Restructure CSS imports to eliminate circular references

### Runtime Errors

**Missing Manifest Entry**:
- **Scenario**: Production view attempts to load a CSS file not in manifest.json
- **Handling**: Laravel Vite helper should throw exception with clear error message
- **Recovery**: Rebuild assets to regenerate manifest with all CSS modules

**404 on CSS Asset**:
- **Scenario**: Browser requests a CSS file that doesn't exist in public/build
- **Handling**: Browser console shows 404 error, page renders without those styles
- **Recovery**: Rebuild assets or verify deployment includes all built CSS files

**CSS Variable Undefined**:
- **Scenario**: View-specific CSS references a CSS variable not defined in base.css
- **Handling**: Browser applies fallback value or ignores the rule
- **Recovery**: Add missing variable to base.css or use fallback syntax

### Migration Errors

**Incomplete Style Migration**:
- **Scenario**: Some styles from app.css or guest.css are not migrated to new files
- **Handling**: Visual regression tests should catch missing styles
- **Recovery**: Identify missing styles and add them to appropriate CSS modules

**Duplicate Style Definitions**:
- **Scenario**: Same styles exist in multiple CSS modules causing conflicts
- **Handling**: CSS cascade rules apply, last loaded file wins
- **Recovery**: Remove duplicate styles, keep only in most appropriate module

**Legacy CSS Still Referenced**:
- **Scenario**: A view still references old app.css or guest.css after migration
- **Handling**: Build succeeds but view may have missing or duplicate styles
- **Recovery**: Update view to reference new CSS modules

## Testing Strategy

### Unit Testing Approach

Unit tests will verify specific examples and edge cases for the CSS architecture migration:

**File Structure Tests**:
- Verify all required CSS files exist at expected paths
- Verify old app.css and guest.css are removed after migration
- Verify vite.config.js contains all CSS module entries

**Content Verification Tests**:
- Verify base.css contains all CSS custom properties
- Verify base.css contains global element styles
- Verify specific selectors migrated to correct files (e.g., `.auth-card` in layouts/guest.css)

**Configuration Tests**:
- Verify Vite config includes base.css as input
- Verify Vite config maintains JavaScript entry points
- Verify Tailwind config remains unchanged

**Build Output Tests**:
- Verify manifest.json exists after production build
- Verify manifest.json contains entries for all CSS modules
- Verify separate CSS files exist in public/build for each module

**Template Tests**:
- Verify login view loads base.css and login.css
- Verify register view loads base.css and register.css
- Verify dashboard view loads base.css and dashboard.css
- Verify welcome view loads base.css and welcome.css

**Documentation Tests**:
- Verify documentation file exists
- Verify documentation contains directory structure explanation
- Verify documentation contains examples for new views
- Verify documentation contains Vite configuration instructions

### Property-Based Testing Approach

Property tests will verify universal behaviors across all inputs using a property-based testing library (e.g., PHPUnit with faker for data generation):

**Property Test Configuration**:
- Minimum 100 iterations per property test
- Each test tagged with feature name and property reference
- Tests use generated data to cover wide input space

**Property 1: CSS Cascade Consistency**
- **Test**: Generate random CSS rule, add to base.css, verify all views reflect change
- **Tag**: Feature: per-view-css-architecture, Property 1: CSS Cascade Consistency
- **Iterations**: 100

**Property 2: View CSS Isolation**
- **Test**: For each view, verify loaded CSS files match expected set (base + layout + view-specific only)
- **Tag**: Feature: per-view-css-architecture, Property 2: View CSS Isolation
- **Iterations**: 100 (25 per view)

**Property 3: Build Output Completeness**
- **Test**: For each CSS module in config, verify corresponding hashed, minified file exists in build output
- **Tag**: Feature: per-view-css-architecture, Property 3: Build Output Completeness
- **Iterations**: 100

**Property 4: Tailwind Integration Preservation**
- **Test**: Add random Tailwind utility class to template, verify it appears in built CSS and is not purged
- **Tag**: Feature: per-view-css-architecture, Property 4: Tailwind Integration Preservation
- **Iterations**: 100

**Property 5: Visual Regression Prevention**
- **Test**: For each view, capture screenshot before and after migration, verify pixel-perfect match
- **Tag**: Feature: per-view-css-architecture, Property 5: Visual Regression Prevention
- **Iterations**: 100 (25 per view)

**Property 6: Hot Module Replacement Functionality**
- **Test**: In dev mode, modify random CSS module, verify browser updates without reload
- **Tag**: Feature: per-view-css-architecture, Property 6: Hot Module Replacement Functionality
- **Iterations**: 100

**Property 7: Manifest Asset Resolution**
- **Test**: For each view in production, verify loaded CSS URLs match manifest entries
- **Tag**: Feature: per-view-css-architecture, Property 7: Manifest Asset Resolution
- **Iterations**: 100

### Testing Tools

- **PHPUnit**: Primary testing framework for both unit and property tests
- **Laravel Dusk**: Browser testing for visual regression and HMR verification
- **CSS Parser**: Parse and validate CSS file contents
- **Faker**: Generate random test data for property tests
- **Percy or BackstopJS**: Visual regression testing tools

### Test Execution Strategy

1. **Pre-migration**: Run full test suite to establish baseline
2. **During migration**: Run unit tests after each file migration step
3. **Post-migration**: Run full property test suite (700+ iterations total)
4. **Continuous**: Run tests on every commit via CI/CD pipeline

### Acceptance Criteria

All tests must pass before migration is considered complete:
- 100% of unit tests passing
- 100% of property tests passing (all 700+ iterations)
- Zero visual regression detected
- Build completes successfully in both dev and production modes
- All views render correctly in browser testing
