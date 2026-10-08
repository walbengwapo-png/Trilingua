<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>TriLingua</title>
    <link rel="icon" href="/favicon.svg" type="image/svg+xml">
    <link rel="icon" href="/favicon.ico" sizes="any">
    @vite(['resources/css/base.css', 'resources/css/views/welcome.css', 'resources/js/app.js'])
    <meta name="csrf-token" content="{{ csrf_token() }}">
</head>
<body>
    <div class="guest-center">
        <div class="hero">
            <div class="left-hero">
                <h1>Translate with TriLingua</h1>
                <p>Fast, accurate translation between English, Cebuano, and Filipino.</p>
                <div class="actions">
                    <a href="{{ route('register') }}" class="btn primary">Get started</a>
                    <a href="{{ route('login') }}" class="btn secondary">Sign in</a>
                </div>
            </div>
            <div class="hero-right">
                <div class="icon-wrap" style="background:transparent;width:64px;height:64px;margin:0">
                    <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                        <circle cx="32" cy="19" r="14.5" fill="none" stroke="#ffffff" stroke-width="11"/>
                        <circle cx="32" cy="19" r="14.5" fill="none" stroke="#3b82f6" stroke-width="8.5"/>
                        <circle cx="20.7" cy="38.5" r="14.5" fill="none" stroke="#ffffff" stroke-width="11"/>
                        <circle cx="20.7" cy="38.5" r="14.5" fill="none" stroke="#10b981" stroke-width="8.5"/>
                        <circle cx="43.3" cy="38.5" r="14.5" fill="none" stroke="#ffffff" stroke-width="11"/>
                        <circle cx="43.3" cy="38.5" r="14.5" fill="none" stroke="#f43f5e" stroke-width="8.5"/>
                        <g transform="rotate(-6 32 32)">
                            <rect x="25.5" y="24" width="13" height="16" rx="3" fill="#ffffff"/>
                            <rect x="28" y="27.5" width="8" height="2.5" rx="1.25" fill="#3b82f6"/>
                            <rect x="28" y="32" width="8" height="2.5" rx="1.25" fill="#cbd5e1"/>
                            <rect x="28" y="36.5" width="6" height="2.5" rx="1.25" fill="#cbd5e1"/>
                        </g>
                    </svg>
                </div>
            </div>
        </div>

        <div class="features">
            <div class="feature-item">
                <div class="icon-wrap">
                    <span class="icon">✦</span>
                </div>
                <h3>Text Translation</h3>
                <p>Translate up to 8,000 characters instantly.</p>
            </div>
            <div class="feature-item">
                <div class="icon-wrap">
                    <span class="icon">📄</span>
                </div>
                <h3>Document Translation</h3>
                <p>Upload and translate DOCX, PDF, TXT, and more.</p>
            </div>
            <div class="feature-item">
                <div class="icon-wrap">
                    <span class="icon">🌐</span>
                </div>
                <h3>Three Languages</h3>
                <p>English, Cebuano, and Filipino — all supported.</p>
            </div>
        </div>
    </div>
</body>
</html>
