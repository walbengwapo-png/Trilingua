@echo off
echo ==========================================
echo   TriLingua - Starting All Services
echo ==========================================
echo.

echo [1/2] Starting Python Translation Server (port 5000)...
start "Python Translation Server" cmd /c "cd /d %~dp0Model && python server.py"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Laravel Web Server (port 8000)...
echo.
echo Open your browser to: http://127.0.0.1:8000
echo.
echo Press Ctrl+C in each window to stop.
echo ==========================================

set PHPRC=C:\php82
C:\php82\php.exe -c C:\php82\php.ini -S 127.0.0.1:8000 -t %~dp0public
pause