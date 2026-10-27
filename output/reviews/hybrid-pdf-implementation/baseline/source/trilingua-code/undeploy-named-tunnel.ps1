<#
.SYNOPSIS
    Undeploy / fully remove the named Cloudflare Tunnel deployment.
.DESCRIPTION
    - Stops the named tunnel + Laravel server (and python/queue if running)
    - Deletes the named tunnel + DNS route from Cloudflare
    - Removes the local cloudflared config dir
    - Restores the pre-deploy .env values (from env.backup.json)
    - Clears the config/view cache
    Leaves all app data (Supabase DB, users, translations) untouched.
.EXAMPLE
    .\undeploy-named-tunnel.ps1 -Hostname demo.example.com
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Hostname
)

$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$demoDir  = Join-Path $root 'storage\demo'
$tunnelDir= Join-Path $demoDir 'tunnel'
$phpPath = (Get-Command php -ErrorAction SilentlyContinue).Source

function Write-Step($m){ Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok($m)  { Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Info($m){ Write-Host "    ..   $m" -ForegroundColor DarkGray }

$cf = @("${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe", "$env:ProgramFiles\cloudflared\cloudflared.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $cf) { $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue; if ($cmd) { $cf = $cmd.Source } }
if (-not $cf) { Write-Info 'cloudflared not found - skipping tunnel deletion' }

$tunnelName = 'tril-' + ($Hostname.Split('.')[0])

# --- 1. Stop the named tunnel process ---
Write-Step 'Stopping named tunnel process'
if (Test-Path (Join-Path $tunnelDir 'tunnel.pid')) {
    $pidFile = Get-Content (Join-Path $tunnelDir 'tunnel.pid')
    if ($pidFile) { Stop-Process -Id $pidFile -Force -ErrorAction SilentlyContinue }
}
# fallback: kill cloudflared running with the runs-on--config tunnel-name
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match $tunnelName } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Ok 'Tunnel process stopped'

# --- 2. Stop Laravel server (and python/queue if running) ---
Write-Step 'Stopping web/python/queue processes'
foreach ($p in @(8000, 5000)) {
    Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}
Get-CimInstance Win32_Process -Filter "Name='php.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'queue:work' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'server\.py|multiprocessing' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Ok 'Processes stopped'

# --- 3. Delete the named tunnel + DNS route from Cloudflare ---
if ($cf) {
    Write-Step "Deleting Cloudflare tunnel '$tunnelName'"
    & $cf tunnel delete $tunnelName -f 2>&1 | Out-String | Write-Info
    & $cf tunnel cleanup $tunnelName -f 2>&1 | Out-String | Write-Info
    Write-Ok 'Tunnel + DNS route removed (DNS CNAME may take a moment to clear globally)'
}

# --- 4. Restore original .env values ---
Write-Step 'Restoring .env from backup'
$envFile = Join-Path $root '.env'
$backupFile = Join-Path $tunnelDir 'env.backup.json'
if (Test-Path $backupFile) {
    $orig = Get-Content $backupFile -Raw | ConvertFrom-Json
    $lines = Get-Content $envFile
    foreach ($prop in $orig.PSObject.Properties) {
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match "^$($prop.Name)=") { $lines[$i] = $prop.Value; break }
        }
    }
    Set-Content -Path $envFile -Value $lines -Encoding ASCII
    Write-Ok '.env restored'
} else { Write-Info "No backup found at $backupFile - .env left unchanged" }

if ($phpPath) {
    Push-Location $root
    & $phpPath artisan config:clear 2>&1 | Out-Null
    & $phpPath artisan config:cache 2>&1 | Out-Null
    & $phpPath artisan view:clear  2>&1 | Out-Null
    Pop-Location
}

# --- 5. Remove local config dir + pid files ---
Write-Step 'Removing local tunnel config'
Remove-Item $tunnelDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $demoDir '*.pid') -ErrorAction SilentlyContinue
Write-Ok 'Local config removed'

Write-Host ''
Write-Host ('=' * 60) -ForegroundColor Yellow
Write-Host '  UNDEPLOYED - fully removable setup removed.' -ForegroundColor Yellow
Write-Host '  Your data (Supabase DB/users/translations) is untouched.' -ForegroundColor Yellow
Write-Host ('=' * 60) -ForegroundColor Yellow
Write-Host ''