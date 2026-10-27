# Implementation Plan: User Settings Feature

## Overview

This plan implements a comprehensive user settings feature for the TriLingua Laravel application. The implementation follows Laravel's MVC pattern and integrates with the existing authentication system. The feature includes account management (name, email, password) and general preferences (theme, language) with immediate theme application and persistent storage.

## Tasks

- [x] 1. Create database migration for settings columns
  - Create migration file to add `theme` and `language` columns to users table
  - Set default values: theme='light', language='en'
  - Run migration to update database schema
  - _Requirements: 5.4, 4.7, 8.4_

- [x] 2. Update User model with new fillable attributes
  - Add `theme` and `language` to fillable array
  - Ensure proper attribute casting if needed
  - _Requirements: 5.1, 5.4_

- [x] 3. Create SettingsController with show method
  - [x] 3.1 Create SettingsController in app/Http/Controllers
    - Generate controller file
    - Implement show() method to display settings page
    - Load authenticated user data
    - _Requirements: 1.2, 1.3, 5.2_
  
  - [x] 3.2 Write unit tests for show method
    - Test authenticated user can access settings page
    - Test unauthenticated user is redirected
    - _Requirements: 1.3_

- [x] 4. Implement account settings update functionality
  - [x] 4.1 Create updateAccount method in SettingsController
    - Validate name and email fields
    - Check email uniqueness (excluding current user)
    - Update user record in database
    - Return with success message
    - _Requirements: 2.3, 2.4, 2.5, 7.1, 7.2_
  
  - [x] 4.2 Write unit tests for account updates
    - Test valid account update succeeds
    - Test email uniqueness validation
    - Test validation error messages
    - _Requirements: 2.6, 7.3_

- [x] 5. Implement password change functionality
  - [x] 5.1 Create updatePassword method in SettingsController
    - Validate current password matches
    - Validate new password meets requirements (min 8 chars)
    - Validate password confirmation matches
    - Hash and save new password
    - Return with success or error messages
    - _Requirements: 3.4, 3.5, 3.6, 3.7, 3.8_
  
  - [x] 5.2 Write unit tests for password changes
    - Test successful password change
    - Test incorrect current password rejection
    - Test password confirmation mismatch
    - Test minimum length validation
    - _Requirements: 3.7, 3.8_

- [x] 6. Implement general settings update functionality
  - [x] 6.1 Create updateGeneral method in SettingsController
    - Validate theme value (light/dark)
    - Validate language value (en/tl/ceb)
    - Update user preferences in database
    - Return with success message
    - _Requirements: 4.4, 4.6, 8.4_
  
  - [x] 6.2 Write unit tests for general settings
    - Test theme update saves correctly
    - Test language update saves correctly
    - Test invalid theme/language values rejected
    - _Requirements: 4.6, 8.5_

- [x] 7. Create settings routes
  - Add GET /settings route for displaying settings page
  - Add POST /settings/account route for account updates
  - Add POST /settings/password route for password changes
  - Add POST /settings/general route for general settings
  - Apply auth middleware to all routes
  - _Requirements: 1.3_

- [x] 8. Create settings view with sidebar layout
  - [x] 8.1 Create settings.blade.php in resources/views
    - Extend main layout
    - Create two-column layout (sidebar + content)
    - Add sidebar navigation with Account and General categories
    - Implement category switching functionality
    - _Requirements: 1.4, 6.1, 6.2, 6.3, 6.4_
  
  - [x] 8.2 Create account settings form section
    - Add name input field with current value
    - Add email input field with current value
    - Add submit button
    - Display success/error messages
    - _Requirements: 2.1, 2.2, 7.4, 7.5_
  
  - [x] 8.3 Create password change form section
    - Add current password input field
    - Add new password input field
    - Add password confirmation input field
    - Add submit button
    - Display success/error messages
    - _Requirements: 3.1, 3.2, 3.3_
  
  - [x] 8.4 Create general settings form section
    - Add theme toggle control (light/dark)
    - Add language dropdown (English, Tagalog, Cebuano)
    - Display current preferences
    - Add submit button
    - _Requirements: 4.1, 4.2, 8.1, 8.2, 8.5_

- [x] 9. Create CSS for settings page
  - [x] 9.1 Create settings.css in resources/css/views
    - Style sidebar navigation
    - Style form layouts and inputs
    - Style success/error messages
    - Ensure responsive design
    - Match existing application styling
    - _Requirements: 6.5, 6.6, 7.5_
  
  - [x] 9.2 Implement theme switching CSS
    - Define CSS custom properties for light theme
    - Define CSS custom properties for dark theme
    - Use data-theme attribute on html element
    - Apply theme variables to all UI elements
    - _Requirements: 4.3, 4.5_

- [x] 10. Update main layout to apply user theme
  - Modify layout blade template to set data-theme attribute
  - Load user's theme preference from database
  - Default to 'light' if no preference set
  - _Requirements: 4.5, 4.7, 5.3_

- [x] 11. Add settings navigation link to sidebar
  - Add settings link to main navigation sidebar
  - Use appropriate icon
  - Highlight active state when on settings page
  - _Requirements: 1.1_

- [x] 12. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The implementation uses Laravel's built-in validation and authentication
- Theme switching uses CSS custom properties for immediate visual feedback
- All forms follow existing application patterns for consistency
