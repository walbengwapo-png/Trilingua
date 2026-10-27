# Design Document: User Settings Feature

## Overview

The user settings feature provides authenticated users with a centralized interface to manage their account information and application preferences. The feature integrates seamlessly with the existing Laravel authentication system and follows the application's established design patterns using Blade templates and custom CSS.

The settings system consists of two primary categories:
- **Account Settings**: Personal information management (name, email, password)
- **General Settings**: Application preferences (theme, language)

The implementation leverages Laravel's built-in validation, authentication, and database features while maintaining consistency with the existing TriLingua application architecture.

## Architecture

### High-Level Architecture

The user settings feature follows Laravel's MVC pattern with these key components:

```
┌─────────────────┐
│  Settings View  │ (Blade Template)
│  - Account Form │
│  - General Form │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ SettingsController│
│  - show()       │
│  - updateAccount()│
│  - updateGeneral()│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   User Model    │
│  - Eloquent ORM │
│  - Validation   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Users Table    │
│  + theme        │
│  + language     │
└─────────────────┘
```

### Component Interaction Flow

1. **Settings Page Access**: User clicks settings link → Route middleware authenticates → Controller loads user data → View renders forms
2. **Account Update**: User submits form → Controller validates → Model updates database → Success message displayed
3. **Theme Change**: User toggles theme → Controller saves preference → CSS variables updated → Theme applied immediately
4. **Password Change**: User submits password form → Controller verifies current password → Validates new password → Hashes and saves

### Database Schema Changes

The existing `users` table requires two new columns:

```sql
ALTER TABLE users ADD COLUMN theme VARCHAR(10) DEFAULT 'light';
ALTER TABLE users ADD COLUMN language VARCHAR(10) DEFAULT 'en';
```

## Components and Interfaces

### 1. SettingsController

**Responsibility**: Handle all settings-related HTTP requests, validation, and business logic.

**Methods**:

```php
class SettingsController extends Controller
{
    // Display the settings page
    public function show(): View
    
    // Update account information (name, email)
    public function updateAccount(Request $request): RedirectResponse
    
    // Update password
    public function updatePassword(Request $request): RedirectResponse
    
    // Update general settings (theme, language)
    public function updateGeneral(Request $request): RedirectResponse
}
```

**Validation Rules**:
- Account: `name` (required, string, max:255), `email` (required, email, unique:users,email,{user_id})
- Password: `current_password` (required, current_password), `password` (required, min:8, confirmed)
- General: `theme` (required, in:light,dark), `language` (required, in:en,tl,ceb)

### 2. Settings View (settings.blade.php)

**Responsibility**: Render the settings interface with sidebar navigation and forms.

**Structure**:
```
┌─────────────────────────────────────┐
│ Settings Page                       │
├──────────┬──────────────────────────┤
│ Sidebar  │ Content Area             │
│          │                          │
│ Account  │ [Active Form Content]    │
│ General  │                          │
│          │                          │
└──────────┴──────────────────────────┘
```

**Key Elements**:
- Sidebar navigation with category links
- Account settings form (name, email)
- Password change form (separate section)
- General settings form (theme toggle, language dropdown)
- Success/error message display areas

### 3. User Model Extension

**Responsibility**: Define fillable attributes and casting for new settings fields.

**Additions**:
```php
protected $fillable = [
    'name',
    'email',
    'password',
    'theme',      // new
    'language',   // new
];

protected $casts = [
    'email_verified_at' => 'datetime',
    'password' => 'hashed',
];
```

### 4. Routes

**Endpoints**:
```php
Route::middleware(['auth'])->group(function () {
    Route::get('/settings', [SettingsController::class, 'show'])->name('settings');
    Route::post('/settings/account', [SettingsController::class, 'updateAccount'])->name('settings.account');
    Route::post('/settings/password', [SettingsController::class, 'updatePassword'])->name('settings.password');
    Route::post('/settings/general', [SettingsController::class, 'updateGeneral'])->name('settings.general');
});
```

### 5. Migration

**File**: `database/migrations/YYYY_MM_DD_HHMMSS_add_settings_to_users_table.php`

**Purpose**: Add theme and language columns to users table.

```php
public function up(): void
{
    Schema::table('users', function (Blueprint $table) {
        $table->string('theme', 10)->default('light')->after('remember_token');
        $table->string('language', 10)->default('en')->after('theme');
    });
}
```

## Data Models

### User Model Attributes

| Attribute | Type | Nullable | Default | Description |
|-----------|------|----------|---------|-------------|
| id | bigint | No | auto | Primary key |
| name | string(255) | No | - | User's display name |
| email | string(255) | No | - | Unique email address |
| email_verified_at | timestamp | Yes | null | Email verification timestamp |
| password | string(255) | No | - | Hashed password |
| remember_token | string(100) | Yes | null | Remember me token |
| theme | string(10) | No | 'light' | UI theme preference |
| language | string(10) | No | 'en' | Interface language |
| created_at | timestamp | No | now() | Record creation time |
| updated_at | timestamp | No | now() | Last update time |

### Request Data Transfer Objects

**AccountUpdateRequest**:
```php
[
    'name' => 'string|required|max:255',
    'email' => 'string|required|email|unique:users,email,{user_id}'
]
```

**PasswordUpdateRequest**:
```php
[
    'current_password' => 'string|required|current_password',
    'password' => 'string|required|min:8|confirmed',
    'password_confirmation' => 'string|required'
]
```

**GeneralSettingsUpdateRequest**:
```php
[
    'theme' => 'string|required|in:light,dark',
    'language' => 'string|required|in:en,tl,ceb'
]
```

### Theme Application

The theme preference is applied through CSS custom properties. The application uses a data attribute on the HTML element:

```html
<html data-theme="{{ auth()->user()->theme ?? 'light' }}">
```

CSS variables are defined for both themes:
```css
[data-theme="light"] {
    --bg: #ffffff;
    --text: #000000;
    --card-bg: #f9fafb;
    /* ... */
}

[data-theme="dark"] {
    --bg: #1a1a1a;
    --text: #ffffff;
    --card-bg: #2d2d2d;
    /* ... */
}
```

