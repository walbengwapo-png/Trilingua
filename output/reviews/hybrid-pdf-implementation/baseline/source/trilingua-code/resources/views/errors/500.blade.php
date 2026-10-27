<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Server Error — TriLingua</title>
    @vite(['resources/css/base.css'])
    <style>
        body { display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; background:var(--bg); font-family:system-ui,sans-serif; }
        .error-page { text-align:center; padding:40px 24px; max-width:480px; }
        .error-page__code { font-size:6rem; font-weight:800; color:var(--border); line-height:1; margin:0; letter-spacing:-0.04em; }
        .error-page__icon { width:64px; height:64px; background:#fef2f2; border-radius:16px; display:flex; align-items:center; justify-content:center; margin:0 auto 24px; color:#ef4444; }
        .error-page__title { font-size:1.5rem; font-weight:700; color:var(--text); margin:16px 0 8px; }
        .error-page__msg { color:var(--muted); font-size:0.9375rem; line-height:1.6; margin:0 0 32px; }
        .error-page__actions { display:flex; gap:12px; justify-content:center; flex-wrap:wrap; }
    </style>
</head>
<body>
<div class="error-page">
    <div class="error-page__icon">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
    </div>
    <p class="error-page__code">500</p>
    <h1 class="error-page__title">Something went wrong</h1>
    <p class="error-page__msg">We ran into an unexpected error. Our team has been notified. Please try again in a moment.</p>
    <div class="error-page__actions">
        <a href="/" class="btn primary">Go to Dashboard</a>
        <a href="javascript:location.reload()" class="btn secondary">Try again</a>
    </div>
</div>
</body>
</html>
