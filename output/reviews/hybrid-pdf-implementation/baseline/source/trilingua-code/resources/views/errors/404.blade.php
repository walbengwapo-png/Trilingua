<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Page Not Found — TriLingua</title>
    @vite(['resources/css/base.css'])
    <style>
        body { display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; background:var(--bg); font-family:system-ui,sans-serif; }
        .error-page { text-align:center; padding:40px 24px; max-width:480px; }
        .error-page__code { font-size:6rem; font-weight:800; color:var(--border); line-height:1; margin:0; letter-spacing:-0.04em; }
        .error-page__icon { width:64px; height:64px; background:#eff6ff; border-radius:16px; display:flex; align-items:center; justify-content:center; margin:0 auto 24px; color:var(--primary); }
        .error-page__title { font-size:1.5rem; font-weight:700; color:var(--text); margin:16px 0 8px; }
        .error-page__msg { color:var(--muted); font-size:0.9375rem; line-height:1.6; margin:0 0 32px; }
        .error-page__actions { display:flex; gap:12px; justify-content:center; flex-wrap:wrap; }
    </style>
</head>
<body>
<div class="error-page">
    <div class="error-page__icon">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            <line x1="11" y1="8" x2="11" y2="11"/><line x1="11" y1="14" x2="11.01" y2="14"/>
        </svg>
    </div>
    <p class="error-page__code">404</p>
    <h1 class="error-page__title">Page not found</h1>
    <p class="error-page__msg">The page you're looking for doesn't exist or has been moved. Let's get you back on track.</p>
    <div class="error-page__actions">
        <a href="/" class="btn primary">Go to Dashboard</a>
        <a href="javascript:history.back()" class="btn secondary">Go back</a>
    </div>
</div>
</body>
</html>
