@echo off
title TriLingua Demo Launcher (public tunnel)
rem ---------------------------------------------------------------
rem  Launches the full TriLingua demo stack with a public HTTPS URL
rem  via Cloudflare quick tunnel:
rem    1. Preflight checks
rem    2. Cloudflare quick tunnel  -> https://xxxx.trycloudflare.com
rem    3. Python translation API   (:5000)
rem    4. Queue worker             (document translations)
rem    5. Laravel web server       (:8000)
rem
rem  The public URL is printed at the end and changes every run.
rem  Stop everything with: stop-demo.ps1
rem
rem  Optional flags can be passed through, e.g.:
rem    start-all-demo-deploy.bat -RebuildAssets
rem    start-all-demo-deploy.bat (add nothing extra = same behavior)
rem ---------------------------------------------------------------
cd /d "%~dp0"
echo Starting TriLingua demo stack...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-demo.ps1" -Tunnel %*
echo.
echo (Window can be closed; processes keep running. Use stop-demo.ps1 to stop.)
pause
