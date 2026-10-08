@echo off
echo ==========================================
echo   TriLingua - Starting All Services
echo ==========================================
echo.

cd /d "%~dp0"
set "PHPRC=C:\php82"
echo Checking for existing TriLingua services...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports = 5000, 8000; $listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort }; $workers = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'php.exe' -and $_.CommandLine -match 'artisan queue:(listen|work)' }; if ($listeners -or $workers) { Write-Host 'Services are already running. Close their windows before restarting; wait for active translations to finish first.'; exit 1 }"
if errorlevel 1 (
    pause
    exit /b 1
)

echo Checking database migrations and deployment configuration...
C:\php82\php.exe -c C:\php82\php.ini artisan deployment:validate-timeouts --check-migrations
if %errorlevel% neq 0 (
    echo FATAL: deployment checks failed. Resolve the errors above before startup.
    pause
    exit /b 1
)

echo [1/4] Starting visible Python Translation Server (port 5000)...
start "TriLingua - Python Translation Server" /D "%~dp0" cmd /k "python -u -m uvicorn server:app --app-dir Model --host 127.0.0.1 --port 5000 --log-level info"

echo Waiting for Python readiness...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline = (Get-Date).AddSeconds(120); while ((Get-Date) -lt $deadline) { try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5000/health' -TimeoutSec 5 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Seconds 2 }; Write-Host 'FATAL: Python did not become healthy. Check its window before restarting.'; exit 1"
if errorlevel 1 (
    pause
    exit /b 1
)

echo [2/4] Starting visible Laravel Queue Listener...
if "%DOCUMENT_QUEUE_WORKERS%"=="" for /f "tokens=1,* delims==" %%a in (.env) do if "%%a"=="DOCUMENT_QUEUE_WORKERS" set "DOCUMENT_QUEUE_WORKERS=%%b"
if "%DOCUMENT_QUEUE_WORKERS%"=="" set DOCUMENT_QUEUE_WORKERS=2
for /L %%i in (1,1,%DOCUMENT_QUEUE_WORKERS%) do start "TriLingua - Laravel Queue Listener %%i" /D "%~dp0" cmd /k "C:\php82\php.exe -c C:\php82\php.ini artisan queue:listen database --tries=3 --timeout=1500 --sleep=1"

echo [3/4] Starting live application log monitor...
start "TriLingua - Live Application Log" /D "%~dp0" cmd /k "powershell -NoProfile -ExecutionPolicy Bypass -Command Get-Content storage\logs\laravel.log -Tail 40 -Wait"

echo [4/4] Starting Laravel Web Server (port 8000)...
echo.
echo Open your browser to: http://127.0.0.1:8000
echo.
echo Press Ctrl+C in each window to stop.
echo ==========================================

C:\php82\php.exe -c C:\php82\php.ini -S 127.0.0.1:8000 -t "%~dp0public"
pause
