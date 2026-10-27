# CSS Not Loading - Troubleshooting Guide

## The Problem

**Symptom**: Your Laravel app shows unstyled HTML (browser default styles) even though you've built the CSS files.

**What You'll See**:
- Dark background (browser default)
- Unstyled form inputs
- No custom colors or layout
- Basic HTML elements only

## Root Cause

Laravel's Vite integration has **two modes**:

1. **Development Mode** (`npm run dev`)
   - Vite dev server runs (usually on port 5173 or 5174)
   - Laravel detects the dev server and tries to load CSS from it
   - Hot reload enabled (changes reflect immediately)

2. **Production Mode** (`npm run build`)
   - CSS compiled to static files in `public/build/`
   - Laravel loads CSS from these static files
   - No hot reload

**The Issue**: When `npm run dev` is running but **not accessible** (wrong port, IPv6 issue, firewall, etc.), Laravel tries to load from the dev server but fails, resulting in no CSS.

## How to Diagnose

### Step 1: Check Browser Console (F12)
Open Developer Tools → Console tab

**Look for**:
- `Failed to load resource: net::ERR_CONNECTION_REFUSED`
- URLs like `http://[::1]:5174/resources/css/guest.css`
- 404 errors for CSS files

### Step 2: Check Network Tab
Developer Tools → Network tab → Refresh page

**Look for**:
- CSS files showing as "failed" or "pending"
- Requests to `localhost:5173` or `localhost:5174`
- Red status codes (404, 500, etc.)

### Step 3: Check What's Running
```bash
# Windows PowerShell
Get-Process | Where-Object {$_.ProcessName -like "*node*"}

# Or check if ports are in use
netstat -ano | findstr "5173"
netstat -ano | findstr "5174"
```

## The Fix (3 Options)

### Option 1: Use Production Build (Simplest)

**When to use**: You don't need hot reload, just want it to work

```bash
# Stop Vite dev server if running (Ctrl+C)

# Build production assets
npm run build

# Refresh browser
# CSS will now load from public/build/
```

**Pros**: Always works, no server needed
**Cons**: Must rebuild after CSS changes

---

### Option 2: Fix Dev Server Connection

**When to use**: You want hot reload during development

```bash
# Stop current dev server (Ctrl+C)

# Start dev server with explicit host
npm run dev -- --host 127.0.0.1

# In another terminal, start Laravel
php artisan serve

# Refresh browser
```

**Pros**: Hot reload works
**Cons**: Need two terminals running

---

### Option 3: Use Production Build During Development

**When to use**: Dev server keeps having issues

**Update `vite.config.js`**:
```javascript
export default defineConfig({
    plugins: [
        laravel({
            input: ['resources/css/app.css', 'resources/css/guest.css', 'resources/js/app.js'],
            refresh: true,
        }),
        tailwindcss(),
    ],
    server: {
        host: '127.0.0.1', // Force IPv4
        port: 5173,
        strictPort: true,
        watch: {
            ignored: ['**/storage/framework/views/**'],
        },
    },
});
```

Then:
```bash
npm run build
php artisan serve
```

---

## Quick Fix Checklist

When CSS stops loading, do this in order:

1. **Stop Vite dev server** (Ctrl+C in terminal running `npm run dev`)
2. **Build production assets**: `npm run build`
3. **Clear Laravel cache**: `php artisan config:clear && php artisan cache:clear`
4. **Hard refresh browser**: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)

## Prevention

### For Development:
```bash
# Terminal 1: Build once and forget
npm run build

# Terminal 2: Run Laravel
php artisan serve

# Rebuild only when you change CSS
npm run build
```

### For Production:
```bash
# Always build before deploying
npm run build

# Commit the public/build/ folder or build during deployment
```

## Common Mistakes

❌ **Running `npm run dev` and forgetting about it**
- Dev server runs in background
- Laravel tries to use it but can't connect
- CSS fails to load

✅ **Solution**: Either use dev server properly OR stop it and use production build

---

❌ **Not rebuilding after CSS changes**
- You edit `resources/css/guest.css`
- Changes don't appear
- Forgot to run `npm run build`

✅ **Solution**: Run `npm run build` after every CSS change (or use `npm run dev` with hot reload)

---

❌ **Browser cache showing old CSS**
- You rebuilt CSS
- Still seeing old styles
- Browser cached the old file

✅ **Solution**: Hard refresh (Ctrl+Shift+R) or clear browser cache

---

## Understanding Vite Modes

### Development Mode (`npm run dev`)
```
Browser → Laravel → Vite Dev Server (localhost:5173) → CSS
                     ↑
                     Must be running and accessible
```

### Production Mode (`npm run build`)
```
Browser → Laravel → public/build/assets/guest-xxx.css
                     ↑
                     Static file, always works
```

## My Recommended Workflow

**For Active CSS Development**:
```bash
# Terminal 1
npm run dev -- --host 127.0.0.1

# Terminal 2
php artisan serve

# Edit CSS, see changes instantly
```

**For Backend Development** (not changing CSS):
```bash
# Build once
npm run build

# Run Laravel
php artisan serve

# Rebuild only when CSS changes
```

**For Production**:
```bash
# Build optimized assets
npm run build

# Deploy (include public/build/ folder)
```

## Debugging Commands

```bash
# Check if CSS file exists
Test-Path public/build/assets/guest-*.css

# Check CSS file size (should be > 0)
(Get-Item public/build/assets/guest-*.css).Length

# Check manifest
Get-Content public/build/manifest.json | ConvertFrom-Json

# Clear all caches
php artisan config:clear
php artisan cache:clear
php artisan view:clear
php artisan route:clear

# Rebuild assets
npm run build
```

## The Fix I Applied

1. **Identified the issue**: Vite dev server was running but Laravel couldn't connect to it (IPv6 issue)
2. **Stopped the dev server**: Killed the `npm run dev` process
3. **Used production build**: The `npm run build` files were already there
4. **Result**: Laravel now loads CSS from `public/build/` instead of trying to connect to dev server

## Summary

**Problem**: Vite dev server running but not accessible → CSS fails to load

**Solution**: Stop dev server, use production build (`npm run build`)

**Prevention**: Choose one mode and stick with it:
- Development: `npm run dev` (both terminals running)
- Production: `npm run build` (static files)

---

**Remember**: When in doubt, just run `npm run build` and refresh your browser! 🎨
