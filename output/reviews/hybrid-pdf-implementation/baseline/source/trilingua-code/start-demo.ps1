<#
.SYNOPSIS
    TriLingua one-command demo launcher.
.EXAMPLE
    .\start-demo.ps1              # Local only   -> http://127.0.0.1:8000
    .\start-demo.ps1 -Tunnel      # Public HTTPS URL via Cloudflare quick tunnel
    .\start-demo.ps1 -RebuildAssets   # Force npm run build first
#>
param(
    [switch]$Tunnel,
    [switch]$RebuildAssets,
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$demoDir = Join-Path $root 'storage\demo'
if (-not (Test-Path $demoDir)) { New-Item -ItemType Directory -Force -Path $demoDir | Out-Null }

function Write-Step($msg)  { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Bad($msg)   { Write-Host "    [FAIL] $msg" -ForegroundColor Red }
function Write-Info($msg)  { Write-Host "    ..   $msg" -ForegroundColor DarkGray }

# ---------------------------------------------------------------------------
# Locate tools
# ---------------------------------------------------------------------------
$php = Get-Command php -ErrorAction SilentlyContinue
if (-not $php) { if (Test-Path 'C:\php82\php.exe') { $phpPath = 'C:\php82\php.exe' } } else { $phpPath = $php.Source }
if (-not $phpPath -and (Test-Path 'C:\php82\php.exe')) { $phpPath = 'C:\php82\php.exe' }
if (-not $phpPath) { Write-Bad 'PHP not found'; exit 1 }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
Write-Step 'Preflight checks'

if (-not (Test-Path (Join-Path $root '.env'))) {
    Write-Bad '.env missing in trilingua-code. Copy it from your original project folder.'
    exit 1
}
Write-Ok '.env present'

if (-not (Test-Path (Join-Path $root 'vendor\autoload.php'))) {
    Write-Bad 'vendor/ missing. Run: composer install'
    exit 1
}
Write-Ok 'vendor/ present'

foreach ($p in @($Port, 5000)) {
    $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if ($conn) { Write-Bad "Port $p already in use. Run .\stop-demo.ps1 first."; exit 1 }
}
Write-Ok "Ports $Port and 5000 are free"

try {
    $null = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5 -UseBasicParsing
    Write-Ok 'Ollama service is running (port 11434)'
} catch {
    Write-Bad 'Ollama is NOT running. Start the Ollama app and re-run.'
    exit 1
}

# ---------------------------------------------------------------------------
# Frontend assets
# ---------------------------------------------------------------------------
$buildDir = Join-Path $root 'public\build'
if ($RebuildAssets -or -not (Test-Path $buildDir)) {
    Write-Step 'Building frontend assets (npm run build)'
    Push-Location $root
    & npm run build 2>&1 | Out-Null
    Pop-Location
    if ($LASTEXITCODE -ne 0) { Write-Bad 'npm run build failed'; exit 1 }
    Write-Ok 'Assets built'
} else {
    Write-Info 'Assets already built (use -RebuildAssets to rebuild)'
}

# ---------------------------------------------------------------------------
# Optional: Cloudflare quick tunnel (must start BEFORE Laravel so APP_URL syncs)
# ---------------------------------------------------------------------------
$tunnelUrl = $null
$tunnelProc = $null
if ($Tunnel) {
    Write-Step 'Starting Cloudflare quick tunnel'
    $cf = @("${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe", "$env:ProgramFiles\cloudflared\cloudflared.exe") |
          Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $cf) { $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue; if ($cmd) { $cf = $cmd.Source } }
    if (-not $cf) { Write-Bad 'cloudflared.exe not found. Install: winget install Cloudflare.cloudflared'; exit 1 }

    $outLog = Join-Path $demoDir 'tunnel.out.log'
    $errLog = Join-Path $demoDir 'tunnel.err.log'
    Remove-Item $outLog, $errLog -ErrorAction SilentlyContinue
    $tunnelProc = Start-Process -FilePath $cf `
        -ArgumentList 'tunnel', '--url', "http://localhost:$Port", '--no-autoupdate' `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog `
        -WindowStyle Hidden -PassThru
    $tunnelProc.Id | Set-Content (Join-Path $demoDir 'tunnel.pid')

    $deadline = (Get-Date).AddSeconds(40)
    while ((Get-Date) -lt $deadline -and -not $tunnelUrl) {
        Start-Sleep -Milliseconds 800
        foreach ($log in @($errLog, $outLog)) {
            if (Test-Path $log) {
                if ((Get-Content $log -Raw -ErrorAction SilentlyContinue) -match '(https://[a-z0-9\-]+\.trycloudflare\.com)') {
                    $tunnelUrl = $Matches[1]; break
                }
            }
        }
    }
    if (-not $tunnelUrl) {
        Write-Bad 'Could not capture tunnel URL within 40s. Check storage\demo\tunnel.err.log'
        exit 1
    }
    Write-Ok "Public URL: $tunnelUrl"
}

# ---------------------------------------------------------------------------
# Sync APP_URL then refresh config cache
# ---------------------------------------------------------------------------
Write-Step 'Syncing APP_URL and caching config'
$appUrl = if ($tunnelUrl) { $tunnelUrl } else { "http://127.0.0.1:$Port" }
$envFile = Join-Path $root '.env'
$lines = Get-Content $envFile
$found = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^APP_URL=') { $lines[$i] = "APP_URL=$appUrl"; $found = $true; break }
}
if (-not $found) { $lines += "APP_URL=$appUrl" }
Set-Content -Path $envFile -Value $lines -Encoding ASCII

Push-Location $root
& $phpPath artisan migrate --force
if ($LASTEXITCODE -ne 0) { Write-Bad 'Migration failed (is Supabase reachable?)'; exit 1 }
& $phpPath artisan deployment:validate-timeouts --check-migrations
if ($LASTEXITCODE -ne 0) { Write-Bad 'Deployment validation failed'; exit 1 }
& $phpPath artisan config:clear 2>&1 | Out-Null
& $phpPath artisan config:cache 2>&1 | Out-Null
& $phpPath artisan view:cache   2>&1 | Out-Null
Pop-Location
Write-Ok "APP_URL=$appUrl | migrations ran | config/view cached"

# ---------------------------------------------------------------------------
# Python translation microservice (:5000)
# ---------------------------------------------------------------------------
Write-Step 'Starting Python translation server'
$pyProc = Start-Process -FilePath 'python' `
    -ArgumentList '-m', 'uvicorn', 'server:app', '--app-dir', 'Model', '--host', '127.0.0.1', '--port', '5000', '--log-level', 'info' `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $demoDir 'python.out.log') `
    -RedirectStandardError (Join-Path $demoDir 'python.err.log') `
    -PassThru
$pyProc.Id | Set-Content (Join-Path $demoDir 'python.pid')

$pyUp = $false
$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5000/health' -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $pyUp = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $pyUp) { Write-Bad 'Python server did not become healthy. See its window / logs.'; exit 1 }
Write-Ok 'Translation API healthy on :5000'

# ---------------------------------------------------------------------------
# Timeout ladder validation (python < job < worker < retry < reconcile)
# ---------------------------------------------------------------------------
Push-Location $root
& $phpPath artisan deployment:validate-timeouts 2>&1 | Out-Null
$timeoutOk = $LASTEXITCODE
Pop-Location
if ($timeoutOk -ne 0) { Write-Bad 'Timeout configuration is unsafe. Fix .env then re-run.'; exit 1 }
Write-Ok 'Timeout ladder validated (deployment:validate-timeouts)'

# ---------------------------------------------------------------------------
# Queue workers (documents translate via database queue)
# ---------------------------------------------------------------------------
Write-Step 'Starting queue worker'
$qPids = @()
$queueWorkers = if ($env:DOCUMENT_QUEUE_WORKERS) {
    [Math]::Max(1, [int]$env:DOCUMENT_QUEUE_WORKERS)
} else { 2 }
for ($i = 1; $i -le $queueWorkers; $i++) {
    $qProc = Start-Process -FilePath $phpPath `
        -ArgumentList 'artisan', 'queue:listen', 'database', '--tries=3', '--timeout=1500', '--sleep=1' `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru
    $qPids += $qProc.Id
}
($qPids -join ',') | Set-Content (Join-Path $demoDir 'queue.pid')
Write-Ok "Queue worker running (PID: $($qPids -join ', '))"

# ---------------------------------------------------------------------------
# Laravel HTTP server
# ---------------------------------------------------------------------------
Write-Step 'Starting Laravel server'
# NOTE: --no-reload is REQUIRED on Windows: without it, ServeCommand strips the
# child process environment and php -S fails with "Failed to listen (reason: ?)".
# Do NOT set PHP_CLI_SERVER_WORKERS here - worker forking is unsupported on
# Windows and the server binds but never answers. Translations run through the
# DB queue anyway, so a single HTTP worker keeps pages responsive.
$srvProc = Start-Process -FilePath $phpPath `
    -ArgumentList 'artisan', 'serve', "--host=0.0.0.0", "--port=$Port", '--no-reload' `
    -WorkingDirectory $root -WindowStyle Minimized -PassThru
$srvProc.Id | Set-Content (Join-Path $demoDir 'serve.pid')

$appUp = $false
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/up" -TimeoutSec 3 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $appUp = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $appUp) { Write-Bad 'Laravel did not come up on /up.'; exit 1 }
Write-Ok 'Web app healthy'

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
$bar = '=' * 62
Write-Host ''
Write-Host $bar -ForegroundColor Yellow
if ($tunnelUrl) {
    Write-Host '  DEMO READY (PUBLIC)' -ForegroundColor Yellow
    Write-Host "  Share this URL : $tunnelUrl"
} else {
    Write-Host '  DEMO READY (LOCAL)' -ForegroundColor Yellow
    Write-Host "  Open           : http://127.0.0.1:$Port"
    Write-Host '  (LAN devices   : http://<this-pc-ip>:'"$Port)"''
}
Write-Host "  Login with an email/password account (Google OAuth will NOT"
Write-Host "  work through the rotating quick-tunnel URL)."
Write-Host $bar -ForegroundColor Yellow
Write-Host "  Stop everything later with: .\stop-demo.ps1"
Write-Host ''
