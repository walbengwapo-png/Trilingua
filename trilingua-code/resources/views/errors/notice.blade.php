<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ $notice['title'] }} - TriLingua</title>
    <style>
        *{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f3f4f6;color:#111827;font:16px/1.6 system-ui,sans-serif;padding:24px}
        main{width:min(100%,480px);padding:32px;background:white;border:1px solid #e5e7eb;border-radius:16px}small{color:#64748b}h1{font-size:25px;line-height:1.3;margin:12px 0}p{color:#475569;margin:12px 0 24px}.actions{display:flex;gap:12px;flex-wrap:wrap}a{display:inline-block;padding:10px 16px;border-radius:8px;color:white;background:#2563eb;text-decoration:none;font-weight:600}a:focus-visible{outline:3px solid #60a5fa;outline-offset:3px}.secondary{background:#eef2f6;color:#334155}.reference{font-size:12px;overflow-wrap:anywhere}
        @media(prefers-color-scheme:dark){body{background:#111827;color:#f9fafb}main{background:#1f2937;border-color:#374151}p,small{color:#cbd5e1}.secondary{background:#374151;color:#f9fafb}}
    </style>
</head>
<body><main>
    <small>TriLingua · {{ $status }}</small>
    <h1>{{ $notice['title'] }}</h1><p>{{ $notice['message'] }}</p>
    @if ($reference)<p class="reference">Reference: {{ $reference }}</p>@endif
    <nav class="actions" aria-label="Next steps">
        @if (in_array($status, [401,419]))
            <a href="{{ route('login') }}">Open sign-in page</a>
        @else
            <a href="{{ route('dashboard') }}">Open dashboard</a>
        @endif
        @unless (in_array($status, [401,419]))
            <a class="secondary" href="{{ route('login') }}">Sign in</a>
        @endunless
    </nav>
</main></body></html>
