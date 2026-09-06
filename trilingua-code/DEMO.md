# TriLingua Demo Runbook

One-command launcher for running TriLingua from this PC as a demo server.

## Quick start

```powershell
cd C:\dev\Trilingua\trilingua-code
.\start-demo.ps1 -Tunnel     # public HTTPS URL (share with audience)
.\start-demo.ps1             # local only -> http://127.0.0.1:8000
```

Stop everything:

```powershell
.\stop-demo.ps1
```

## What start-demo.ps1 does, in order

1. Preflight: `.env` present, `vendor/` present, ports free, Ollama alive
2. Builds frontend assets if `public/build` is missing (`-RebuildAssets` forces it)
3. Starts Cloudflare quick tunnel first, captures the `*.trycloudflare.com` URL
4. Rewrites `APP_URL` in `.env`, runs migrations, caches config+views
5. Starts Python translation API (`:5000`) and waits for health
6. Starts queue worker (document translations run through the DB queue)
7. Starts Laravel (`php artisan serve --host=0.0.0.0`, 4 workers)
8. Prints a banner with the URL(s)

## Pre-demo checklist (2 minutes)

- [ ] Ollama app is running (system tray icon)
- [ ] Internet connected (Supabase, Mistral, Ollama Cloud, tunnel all need it)
- [ ] `.\start-demo.ps1 -Tunnel` printed **DEMO READY**
- [ ] Opened the URL once on your phone to confirm it loads from outside
- [ ] Logged in with an **email/password** account

> Google OAuth will NOT work through the rotating quick-tunnel URL — each new
> session gets a new hostname and Google rejects unknown redirect URIs.
> Always demo with email/password accounts.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Port 8000 already in use` | Run `.\stop-demo.ps1`, then retry |
| `Ollama is NOT running` | Launch the Ollama desktop app, wait ~10 s, retry |
| Tunnel URL never appears | Check `storage\demo\tunnel.err.log`; usually corporate WiFi/VPN blocking outbound :443 — try phone hotspot |
| Translation spins forever | Is Ollama signed in? Test: `ollama run gpt-oss:20b-cloud "hi"` |
| Document translation stuck "processing" | Queue worker died — rerun `.\start-demo.ps1` (it restarts one) |
| `Migration failed` | Supabase project paused or offline internet — restore project at supabase.com |
| Page shows mixed-content / broken CSS on tunnel URL | Re-run script; APP_URL sync step must run AFTER tunnel starts (script handles order) |

## Files & logs

| Path | Purpose |
|---|---|
| `storage\demo\tunnel.err.log` | cloudflared output incl. generated URL |
| `storage\demo\*.pid` | PIDs of launched processes |
| Python/queue/serve windows | Minimized windows; close via stop-demo.ps1 only |

## Notes

- The quick-tunnel URL **changes every run** — expect that, it's normal.
- Everything binds locally except `php artisan serve` which listens on
  `0.0.0.0` so LAN devices can also reach `http://<your-pc-ip>:8000`
  without any tunnel (handy fallback if Cloudflare is blocked).
---

## Stable named tunnel (optional — for real demos / stable logins)

The quick tunnel above gets a **new random hostname every run**, which breaks
session cookies and CSRF (users see "page expired" / logins drop). For a demo
with a custom domain, use the named-tunnel scripts instead:

```powershell
# one-time: authorize Cloudflare (opens a browser)
cloudflared tunnel login

# deploy (requires your domain zone added to your Cloudflare account)
.\deploy-named-tunnel.ps1 -Hostname demo.yourdomain.com -Zone yourdomain.com

# include the Python service + 3 DB queue workers for full document translation
.\deploy-named-tunnel.ps1 -Hostname demo.yourdomain.com -Zone yourdomain.com -StartPythonQueue

# fully remove everything (stops processes, deletes tunnel/DNS, restores .env)
.\undeploy-named-tunnel.ps1 -Hostname demo.yourdomain.com
```

What it does:
- Creates a named `cloudflared` tunnel + DNS `CNAME` to your hostname (static URL)
- Points ingress at the local Laravel server (`http://127.0.0.1:8000`)
- Sets the hostname-dependent `.env` values (`APP_URL`, `SESSION_DOMAIN`,
  `SESSION_SECURE_COOKIE=true`, `GOOGLE_REDIRECT_URI`) and re-caches config
- Backs up the original `.env` values to `storage\demo\tunnel\env.backup.json`
  so `undeploy-named-tunnel.ps1` can restore them

Enable Google login on the stable URL by adding this to the Google OAuth
console (authorized redirect URI): `https://demo.yourdomain.com/auth/google/callback`

Templates/config live under `storage\demo\tunnel\` and are removed on undeploy.
Your data (Supabase DB/users/translations) is never touched.
