# Password Reset Functionality

## ✅ Implementation Complete

The forgot password / password reset functionality has been fully implemented for TriLingua.

## How It Works

### For Users:

1. **Forgot Password Page**
   - Go to the login page
   - Click "Forgot password?" link
   - Enter your email address
   - Click "Send reset link"

2. **Check Email (Development Mode)**
   - In development, emails are logged to `storage/logs/laravel.log`
   - Look for the password reset link in the log file
   - The link looks like: `http://localhost:8000/reset-password/{token}?email={email}`

3. **Reset Password**
   - Click the link from the email (or copy it from the log)
   - Enter your new password
   - Confirm the password
   - Click "Reset password"
   - You'll be redirected to login with a success message

### Routes Added:

- `GET /forgot-password` - Show forgot password form
- `POST /forgot-password` - Send reset link email
- `GET /reset-password/{token}` - Show reset password form
- `POST /reset-password` - Process password reset

### Files Created:

- `app/Http/Controllers/Auth/ForgotPasswordController.php`
- `app/Http/Controllers/Auth/ResetPasswordController.php`
- `app/Notifications/ResetPasswordNotification.php`
- `resources/views/auth/forgot-password.blade.php`
- `resources/views/auth/reset-password.blade.php`

### Files Modified:

- `routes/web.php` - Added password reset routes
- `resources/views/auth/login.blade.php` - Updated forgot password link
- `resources/css/views/auth/login.css` - Added alert styles
- `app/Models/User.php` - Added custom password reset notification
- `.env` - Updated APP_NAME and MAIL_FROM_ADDRESS

## Testing in Development

Since emails are logged (not sent), follow these steps to test:

1. Go to http://localhost:8000/forgot-password
2. Enter: `kusa_230000002006@uic.edu.ph`
3. Click "Send reset link"
4. Open `storage/logs/laravel.log`
5. Find the reset link (search for "reset-password")
6. Copy the full URL and paste it in your browser
7. Enter a new password and confirm
8. Log in with the new password

## Production Setup

To use real email in production:

1. Update `.env` with your email service credentials:
   ```env
   MAIL_MAILER=smtp
   MAIL_HOST=smtp.mailtrap.io
   MAIL_PORT=2525
   MAIL_USERNAME=your-username
   MAIL_PASSWORD=your-password
   MAIL_ENCRYPTION=tls
   ```

2. Popular email services:
   - **Mailtrap** (testing): https://mailtrap.io
   - **SendGrid**: https://sendgrid.com
   - **Mailgun**: https://mailgun.com
   - **Amazon SES**: https://aws.amazon.com/ses/
   - **Gmail SMTP** (not recommended for production)

## Security Features

- ✅ Rate limiting (10 requests per minute)
- ✅ Token expiration (60 minutes)
- ✅ Throttling to prevent abuse
- ✅ Secure token generation
- ✅ Password confirmation required
- ✅ Session regeneration after reset

## Customization

### Change Token Expiration

Edit `config/auth.php`:
```php
'passwords' => [
    'users' => [
        'expire' => 60, // Change to desired minutes
    ],
],
```

### Change Email Template

Edit `app/Notifications/ResetPasswordNotification.php` to customize the email content.

### Change Styling

Edit `resources/css/views/auth/login.css` to customize the look and feel.
