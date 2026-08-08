<!doctype html>
<html lang="en" data-theme="light">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script>
        (function () {
            var t = 'light';
            try { t = localStorage.getItem('trilingua-theme') || 'light'; } catch (e) {}
            document.documentElement.dataset.theme = (t === 'dark') ? 'dark' : 'light';
        })();
    </script>
    <title>@yield('title', 'TriLingua') — TriLingua</title>
    <link rel="icon" href="/favicon.svg" type="image/svg+xml">
    <link rel="icon" href="/favicon.ico" sizes="any">
    @vite(['resources/css/base.css', 'resources/css/layouts/guest.css', 'resources/js/app.js'])
    @yield('styles')
    <meta name="csrf-token" content="{{ csrf_token() }}">
</head>
<body class="auth-body">
<div class="auth-container">

    {{-- Left branding panel --}}
    <div class="auth-brand">
        {{-- Animated canvas background --}}
        <canvas class="auth-brand__canvas" aria-hidden="true"></canvas>

        {{-- Animated gradient mesh blobs --}}
        <div class="auth-brand__blob auth-brand__blob--1" aria-hidden="true"></div>
        <div class="auth-brand__blob auth-brand__blob--2" aria-hidden="true"></div>
        <div class="auth-brand__blob auth-brand__blob--3" aria-hidden="true"></div>

        <div class="auth-brand__logo">
            <div class="auth-brand__logo-icon">
                <svg width="28" height="28" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
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
            <span class="auth-brand__logo-name">TriLingua</span>
        </div>

        <div class="auth-brand__tagline">
            <h2>Translate across<br>three languages</h2>
            <p>Powered by NLLB-200 AI — translate text and documents between English, Cebuano, and Filipino instantly.</p>

            <div class="auth-brand__langs">
                <span class="auth-brand__lang-pill">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                    English
                </span>
                <span class="auth-brand__lang-pill">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                    Cebuano
                </span>
                <span class="auth-brand__lang-pill">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                    Filipino
                </span>
            </div>
        </div>
    </div>

    {{-- Right form panel --}}
    <div class="auth-card">
        <div class="auth-card-inner">
            @yield('content')
        </div>
    </div>

</div>
@yield('scripts')
<script>
(function () {
    var canvas = document.querySelector('.auth-brand__canvas');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var particles = [];
    var mouse = { x: null, y: null };

    function resize() {
        canvas.width  = canvas.offsetWidth;
        canvas.height = canvas.offsetHeight;
    }

    function Particle() {
        this.reset();
    }

    Particle.prototype.reset = function () {
        this.x  = Math.random() * canvas.width;
        this.y  = Math.random() * canvas.height;
        this.r  = Math.random() * 2 + 0.5;
        this.vx = (Math.random() - 0.5) * 0.4;
        this.vy = (Math.random() - 0.5) * 0.4;
        this.alpha = Math.random() * 0.5 + 0.1;
    };

    Particle.prototype.update = function () {
        this.x += this.vx;
        this.y += this.vy;
        if (this.x < 0 || this.x > canvas.width)  this.vx *= -1;
        if (this.y < 0 || this.y > canvas.height)  this.vy *= -1;
    };

    Particle.prototype.draw = function () {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255,255,255,' + this.alpha + ')';
        ctx.fill();
    };

    function init() {
        resize();
        var count = Math.floor((canvas.width * canvas.height) / 8000);
        count = Math.min(Math.max(count, 20), 80);
        particles = [];
        for (var i = 0; i < count; i++) {
            particles.push(new Particle());
        }
    }

    function drawConnections() {
        for (var i = 0; i < particles.length; i++) {
            for (var j = i + 1; j < particles.length; j++) {
                var dx   = particles[i].x - particles[j].x;
                var dy   = particles[i].y - particles[j].y;
                var dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 100) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = 'rgba(255,255,255,' + (0.12 * (1 - dist / 100)) + ')';
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
            // Connect to mouse
            if (mouse.x !== null) {
                var mdx  = particles[i].x - mouse.x;
                var mdy  = particles[i].y - mouse.y;
                var mdist = Math.sqrt(mdx * mdx + mdy * mdy);
                if (mdist < 140) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(mouse.x, mouse.y);
                    ctx.strokeStyle = 'rgba(255,255,255,' + (0.22 * (1 - mdist / 140)) + ')';
                    ctx.lineWidth = 0.6;
                    ctx.stroke();
                }
            }
        }
    }

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        drawConnections();
        for (var i = 0; i < particles.length; i++) {
            particles[i].update();
            particles[i].draw();
        }
        requestAnimationFrame(animate);
    }

    canvas.addEventListener('mousemove', function (e) {
        var rect = canvas.getBoundingClientRect();
        mouse.x = e.clientX - rect.left;
        mouse.y = e.clientY - rect.top;
    });
    canvas.addEventListener('mouseleave', function () {
        mouse.x = null; mouse.y = null;
    });

    window.addEventListener('resize', function () {
        init();
    });

    init();
    animate();
})();
</script>
</body>
</html>
