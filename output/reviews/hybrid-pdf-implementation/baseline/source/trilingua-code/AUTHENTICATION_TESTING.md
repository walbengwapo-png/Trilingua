# Authentication Testing Guide

## Quick Start

Your authentication system is now fully secured and ready to use! Here's how to test it:

### 1. Start the Development Server

```bash
php artisan serve
```

The application will be available at `http://localhost:8000`

### 2. Test Registration

1. Navigate to `http://localhost:8000/register`
2. Fill in the form:
   - **Name**: Your full name (letters and spaces only)
   - **Email**: Valid email address
   - **Password**: Must meet requirements:
     - At least 8 characters
     - Contains uppercase letters
     - Contains lowercase letters
     - Contains numbers
     - Contains symbols (e.g., !@#$%^&*)
   - **Confirm Password**: Must match password
3. Click "Sign up"
4. You'll be automatically logged in and redirected to the dashboard

### 3. Test Login

1. Navigate to `http://localhost:8000/login`
2. Enter your email and password
3. Optionally check "Remember me"
4. Click "Sign in"
5. You'll be redirected to the dashboard

### 4. Test Security Features

#### Rate Limiting
Try logging in with wrong credentials 6 times:
- First 5 attempts: "The provided credentials do not match our records."
- 6th attempt: "Too many login attempts. Please try again in 15 minutes."

#### Session Security
1. Login successfully
2. Open browser DevTools → Application → Cookies
3. Verify cookies are:
   - `HttpOnly`: ✓ (prevents JavaScript access)
   - `Secure`: ✓ (HTTPS only in production)
   - `SameSite`: Lax (CSRF protection)

#### Password Validation
Try registering with weak passwords:
- "password" → Error: Must contain uppercase, numbers, symbols
- "Pass123" → Error: Must contain symbols
- "Pass@123" → ✓ Accepted

### 5. Test Logout

1. While logged in, click "Logout"
2. Session is invalidated
3. You're redirected to login page
4. Try accessing `/dashboard` → Redirected to login

## API Testing with cURL

### Register a New User
```bash
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=John Doe" \
  -d "email=john@example.com" \
  -d "password=SecurePass123!" \
  -d "password_confirmation=SecurePass123!" \
  -c cookies.txt
```

### Login
```bash
curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=john@example.com" \
  -d "password=SecurePass123!" \
  -c cookies.txt
```

### Access Protected Route
```bash
curl http://localhost:8000/dashboard \
  -b cookies.txt
```

### Logout
```bash
curl -X POST http://localhost:8000/logout \
  -b cookies.txt
```

## Database Verification

### Check if User was Created
```bash
php artisan tinker
```

Then in tinker:
```php
User::all(); // See all users
User::where('email', 'john@example.com')->first(); // Find specific user
```

### Check Sessions Table
```php
DB::table('sessions')->get(); // See active sessions
```

## Security Monitoring

### View Security Logs
```bash
# Windows
type storage\logs\laravel.log | findstr /i "login lockout session"

# Or open in text editor
notepad storage\logs\laravel.log
```

Look for:
- `Login lockout` - Brute force attempts
- `Session hijacking attempt detected` - Security violations
- `User IP address changed` - IP changes
- `New user registered` - New registrations

## Common Issues & Solutions

### Issue: "Migration table not found"
**Solution:**
```bash
php artisan migrate
```

### Issue: "CSRF token mismatch"
**Solution:**
- Clear browser cache
- Ensure cookies are enabled
- Check that forms include `@csrf` directive

### Issue: "Session not persisting"
**Solution:**
- Check `SESSION_DRIVER=database` in .env
- Run `php artisan migrate` to create sessions table
- Clear cache: `php artisan cache:clear`

### Issue: "Too many login attempts" (testing)
**Solution:**
Wait 15 minutes or clear rate limiter:
```bash
php artisan cache:clear
```

## Production Checklist

Before deploying to production:

1. **Environment Configuration**
   ```env
   APP_ENV=production
   APP_DEBUG=false
   SESSION_SECURE_COOKIE=true
   ```

2. **HTTPS Setup**
   - Configure SSL certificate
   - Force HTTPS in web server config
   - Update `APP_URL` to https://

3. **Database**
   - Run migrations: `php artisan migrate --force`
   - Set up automated backups
   - Enable connection pooling

4. **Security**
   - Review security logs regularly
   - Set up monitoring alerts
   - Configure firewall rules
   - Enable database encryption

5. **Performance**
   - Cache configuration: `php artisan config:cache`
   - Cache routes: `php artisan route:cache`
   - Optimize autoloader: `composer install --optimize-autoloader --no-dev`

## Success Indicators

✅ **Registration Works**: User created in database, automatically logged in
✅ **Login Works**: Session created, redirected to dashboard
✅ **Logout Works**: Session destroyed, redirected to login
✅ **Rate Limiting Works**: Locked out after 5 failed attempts
✅ **Password Validation Works**: Weak passwords rejected
✅ **Session Security Works**: User agent validation, IP logging
✅ **CSRF Protection Works**: Forms require valid CSRF token

## Next Steps

1. Customize the dashboard page
2. Add password reset functionality
3. Implement email verification
4. Add two-factor authentication (2FA)
5. Set up social login (Google, Twitter, Apple)
6. Configure email notifications
7. Add user profile management

Your authentication system is production-ready with enterprise-grade security! 🔒
