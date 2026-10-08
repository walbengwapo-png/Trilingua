<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * Feature tests for SettingsController::show()
 *
 * Validates: Requirements 1.3
 *
 * Requirement 1.3: THE Settings_Page SHALL be accessible only to authenticated users.
 */
class SettingsControllerTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Test that an authenticated user can access the settings page.
     *
     * An authenticated user making a GET request to /settings should receive
     * a 200 OK response and see the settings view.
     */
    public function test_authenticated_user_can_access_settings_page(): void
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)->get('/settings');

        $response->assertStatus(200);
        $response->assertViewIs('settings');
    }

    /**
     * Test that the settings view receives the authenticated user's data.
     *
     * The view should have access to the current user so it can display
     * their name, email, and preferences.
     */
    public function test_settings_page_passes_user_to_view(): void
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)->get('/settings');

        $response->assertStatus(200);
        $response->assertViewHas('user', $user);
    }

    /**
     * Test that an unauthenticated user is redirected away from the settings page.
     *
     * A guest (unauthenticated) user making a GET request to /settings should
     * be redirected, typically to the login page.
     */
    public function test_unauthenticated_user_is_redirected_from_settings(): void
    {
        $response = $this->get('/settings');

        $response->assertRedirect('/login');
    }

    /**
     * Test that an unauthenticated user receives a redirect (not 200) status.
     *
     * Ensures the auth middleware is applied to the settings route.
     */
    public function test_unauthenticated_user_cannot_view_settings(): void
    {
        $response = $this->get('/settings');

        $response->assertStatus(302);
    }

    // -------------------------------------------------------------------------
    // updateAccount tests
    //
    // Validates: Requirements 2.6, 7.3
    //
    // Requirement 2.6: IF validation fails, THEN THE Settings_System SHALL
    //   display error messages for invalid fields.
    // Requirement 7.3: IF validation fails, THEN THE Settings_System SHALL
    //   display error messages next to the relevant fields.
    // -------------------------------------------------------------------------

    /**
     * Test that a valid POST to /settings/account updates name and email
     * and redirects back with a success message.
     *
     * Requirement 2.4: When validation passes, the system SHALL save the
     * updated account information to the database.
     * Requirement 2.5: When account information is successfully updated,
     * the system SHALL display a success message.
     */
    public function test_valid_account_update_succeeds(): void
    {
        $user = User::factory()->create([
            'name'  => 'Old Name',
            'email' => 'old@example.com',
        ]);

        $response = $this->actingAs($user)->post('/settings/account', [
            'name'  => 'New Name',
            'email' => 'new@example.com',
        ]);

        $response->assertRedirect();
        $response->assertSessionHas('success');

        $this->assertDatabaseHas('users', [
            'id'    => $user->id,
            'name'  => 'New Name',
            'email' => 'new@example.com',
        ]);
    }

    /**
     * Test that submitting an email already used by another user fails
     * with a validation error on the email field.
     *
     * Requirement 2.6 / 7.3: Validation failure must surface field-level errors.
     */
    public function test_email_uniqueness_validation_fails_for_another_users_email(): void
    {
        $existingUser = User::factory()->create(['email' => 'taken@example.com']);
        $user         = User::factory()->create(['email' => 'mine@example.com']);

        $response = $this->actingAs($user)->post('/settings/account', [
            'name'  => 'My Name',
            'email' => 'taken@example.com',
        ]);

        $response->assertSessionHasErrors(['email']);
    }

    /**
     * Test that a user can keep their own email without triggering a
     * uniqueness validation error.
     *
     * The unique rule must exclude the current user's own record.
     */
    public function test_user_can_keep_their_own_email(): void
    {
        $user = User::factory()->create([
            'name'  => 'My Name',
            'email' => 'mine@example.com',
        ]);

        $response = $this->actingAs($user)->post('/settings/account', [
            'name'  => 'Updated Name',
            'email' => 'mine@example.com',
        ]);

        $response->assertRedirect();
        $response->assertSessionHas('success');
        $response->assertSessionMissing('errors');
    }

    /**
     * Test that the name field is required.
     *
     * Requirement 2.6 / 7.3: Missing required fields must produce validation errors.
     */
    public function test_name_is_required(): void
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)->post('/settings/account', [
            'name'  => '',
            'email' => $user->email,
        ]);

        $response->assertSessionHasErrors(['name']);
    }

    /**
     * Test that the email field must be a valid email format.
     *
     * Requirement 2.6 / 7.3: Invalid email format must produce a validation error.
     */
    public function test_email_must_be_valid_format(): void
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)->post('/settings/account', [
            'name'  => 'My Name',
            'email' => 'not-an-email',
        ]);

        $response->assertSessionHasErrors(['email']);
    }

    // -------------------------------------------------------------------------
    // updatePassword tests
    //
    // Validates: Requirements 3.7, 3.8
    //
    // Requirement 3.7: IF the current password is incorrect, THEN THE
    //   Settings_System SHALL display an error message.
    // Requirement 3.8: IF the new password confirmation does not match, THEN
    //   THE Settings_System SHALL display an error message.
    // -------------------------------------------------------------------------

    /**
     * Test that a valid password change request succeeds.
     *
     * Providing the correct current password, a valid new password (min 8 chars),
     * and a matching confirmation should update the password and redirect with
     * a success message.
     *
     * Requirement 3.4 / 3.5 / 3.6: Verify current password, validate new
     * password requirements, then hash and save.
     */
    public function test_successful_password_change(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('OldPassword1'),
        ]);

        $response = $this->actingAs($user)->post('/settings/password', [
            'current_password'      => 'OldPassword1',
            'password'              => 'NewPassword1',
            'password_confirmation' => 'NewPassword1',
        ]);

        $response->assertRedirect();
        $response->assertSessionHas('password_success');

        // Verify the password was actually changed in the database.
        $this->assertTrue(
            \Illuminate\Support\Facades\Hash::check('NewPassword1', $user->fresh()->password)
        );
    }

    /**
     * Test that an incorrect current password is rejected.
     *
     * Submitting the wrong current password must produce a validation error
     * on the current_password field and must NOT update the password.
     *
     * Requirement 3.7: IF the current password is incorrect, THEN THE
     *   Settings_System SHALL display an error message.
     */
    public function test_incorrect_current_password_is_rejected(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('CorrectPassword1'),
        ]);

        $response = $this->actingAs($user)->post('/settings/password', [
            'current_password'      => 'WrongPassword1',
            'password'              => 'NewPassword1',
            'password_confirmation' => 'NewPassword1',
        ]);

        $response->assertSessionHasErrors(['current_password']);

        // Password must remain unchanged.
        $this->assertTrue(
            \Illuminate\Support\Facades\Hash::check('CorrectPassword1', $user->fresh()->password)
        );
    }

    /**
     * Test that a password confirmation mismatch fails validation.
     *
     * When the new password and its confirmation do not match, a validation
     * error must be returned on the password field.
     *
     * Requirement 3.8: IF the new password confirmation does not match, THEN
     *   THE Settings_System SHALL display an error message.
     */
    public function test_password_confirmation_mismatch_fails(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('OldPassword1'),
        ]);

        $response = $this->actingAs($user)->post('/settings/password', [
            'current_password'      => 'OldPassword1',
            'password'              => 'NewPassword1',
            'password_confirmation' => 'DifferentPassword1',
        ]);

        $response->assertSessionHasErrors(['password']);
    }

    /**
     * Test that a new password shorter than 8 characters fails validation.
     *
     * The minimum length requirement must be enforced; passwords with fewer
     * than 8 characters must produce a validation error on the password field.
     *
     * Requirement 3.5: Validate the new password meets security requirements
     *   (minimum 8 characters).
     */
    public function test_new_password_minimum_length_validation(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('OldPassword1'),
        ]);

        $response = $this->actingAs($user)->post('/settings/password', [
            'current_password'      => 'OldPassword1',
            'password'              => 'short',
            'password_confirmation' => 'short',
        ]);

        $response->assertSessionHasErrors(['password']);
    }

    // -------------------------------------------------------------------------
    // updateGeneral tests
    //
    // Validates: Requirement 4.6
    //
    // Requirement 4.6: THE Settings_System SHALL support two theme options:
    //   light and dark.
    // -------------------------------------------------------------------------

    /**
     * Test that a valid theme update saves to the database and redirects with success.
     *
     * Submitting a valid theme value ('light' or 'dark') must persist the value
     * to the users table and redirect back with a general_success flash message.
     *
     * Requirement 4.4: When a User selects a theme, THE Settings_System SHALL
     *   save the theme preference to the database.
     * Requirement 4.6: THE Settings_System SHALL support two theme options: light and dark.
     */
    public function test_valid_theme_update_saves_to_database_and_redirects_with_success(): void
    {
        $user = User::factory()->create(['theme' => 'light']);

        $response = $this->actingAs($user)->post('/settings/general', [
            'theme' => 'dark',
        ]);

        $response->assertRedirect();
        $response->assertSessionHas('general_success');

        $this->assertDatabaseHas('users', [
            'id'    => $user->id,
            'theme' => 'dark',
        ]);
    }

    /**
     * Test that an invalid theme value is rejected with a validation error.
     *
     * Only 'light' and 'dark' are accepted theme values. Any other value
     * (e.g. 'blue') must produce a validation error on the theme field.
     *
     * Requirement 4.6: THE Settings_System SHALL support two theme options:
     *   light and dark.
     */
    public function test_invalid_theme_value_is_rejected(): void
    {
        $user = User::factory()->create(['theme' => 'light']);

        $response = $this->actingAs($user)->post('/settings/general', [
            'theme' => 'blue',
        ]);

        $response->assertSessionHasErrors(['theme']);

        // The database value must remain unchanged.
        $this->assertDatabaseHas('users', [
            'id'    => $user->id,
            'theme' => 'light',
        ]);
    }

    /**
     * Test that the settings view no longer renders a language preference field.
     *
     * Requirement: THE Settings_System SHALL NOT expose a language preference.
     */
    public function test_settings_view_has_no_language_field(): void
    {
        $user = User::factory()->create(['theme' => 'light']);

        $response = $this->actingAs($user)->get('/settings');

        $response->assertOk();
        $response->assertDontSee('name="language"', false);
        $response->assertDontSee('>Language</label>', false);
    }
}
