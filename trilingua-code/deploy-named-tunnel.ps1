<#
.SYNOPSIS
    Deploy TriLingua behind a STABLE named Cloudflare Tunnel (replaces the
    rotating quick-tunnel so sessions/CSRF stop expiring).
.DESCRIPTION
    Creates (or reuses) a cloudflared named tunnel, wires a DNS CNAME, points
    ingress at local Laravel, and updates hostname-dependent .env values
    (APP_URL, SESSION_DOMAIN, SESSION_SECURE_COOKIE, GOOGLE_REDIRECT_URI).
    Requires a domain zone already added to your Cloudflare account.
    Run `cloudflared tunnel login` once interactively to authorize.
.EXAMPLE
    .\deploy-named-tunnel.ps1 -Hostname demo.example.com -Zone example.com
    .\deploy-named-tunnel.ps1 -Hostname demo.example.com -Zone example.com -StartPythonQueue
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Hostname,         # e.g. demo.example.com
    [Parameter(Mandatory = $true)]
    [string]$Zone,             # e.g. example.com (apex, used for SESSION_DOMAIN)
    [switch]$StartPythonQueue, # also boot Python service + 3 DB queue workers
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$demoDir  = Join-Path $root 'storage\demo'
$tunnelDir= Join-Path $demoDir 'tunnel'
if (-not (Get-Command php -ErrorAction SilentlyContinue)) { Write-Host '[FAIL] PHP not found on PATH'; exit 1 }
$phpPath = (Get-Command php).Source

function Write-Step($m){ Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok($m)  { Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Bad($m) { Write-Host "    [FAIL] $m" -ForegroundColor Red }
function Write-Info($m){ Write-Host "    ..   $m" -ForegroundColor DarkGray }

# --- Locate cloudflared ---
$cf = @("${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe", "$env:ProgramFiles\cloudflared\cloudflared.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $cf) { $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue; if ($cmd) { $cf = $cmd.Source } }
if (-not $cf) { Write-Bad 'cloudflared.exe not found. Install: winget install Cloudflare.cloudflared'; exit 1 }
Write-Ok "cloudflared: $cf"

$tunnelName = 'tril-' + ($Hostname.Split('.')[0])
New-Item -ItemType Directory -Force -Path $tunnelDir | Out-Null

# --- 1. Ensure authenticated with Cloudflare (interactive, one-time) ---
$cert = Join-Path $env:USERPROFILE '.cloudflared\cert.pem'
if (-not (Test-Path $cert)) {
    Write-Step 'Cloudflare login required (one-time, interactive)'
    Write-Info 'A browser window will open - authorize your Cloudflare account.'
    & $cf tunnel login
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $cert)) { Write-Bad 'Login failed/aborted'; exit 1 }
}
Write-Ok 'Cloudflare login present'

# --- 2. Create/reuse the named tunnel ---
Write-Step "Ensuring tunnel '$tunnelName'"
$tunnelList = (& $cf tunnel list 2>$null) -join "`n"
if ($tunnelList -notmatch "$tunnelName") {
    & $cf tunnel create $tunnelName | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Bad 'Could not create tunnel'; exit 1 }
}
$tunnelId = $null
Get-ChildItem (Join-Path $env:USERPROFILE '.cloudflared\*.json') -ErrorAction SilentlyContinue | ForEach-Object {
    $j = Get-Content $_.FullName -Raw | ConvertFrom-Json
    if ($j.TunnelName -eq $tunnelName) { $tunnelId = $j.TunnelID; $srcJson = $_.FullName }
}
if (-not $tunnelId) { Write-Bad 'Tunnel created but its credentials JSON was not found'; exit 1 }
Write-Info "Tunnel ID: $tunnelId"
Copy-Item $srcJson (Join-Path $tunnelDir 'credentials.json') -Force
Write-Ok "Tunnel ready: $tunnelName ($tunnelId)"
# --- 3. Write the cloudflared ingress config ---
$cfgPath = Join-Path $tunnelDir 'config.yml'
$credPath = ($tunnelDir -replace '\\','\') + '\credentials.json'
@"
tunnel: $tunnelName
credentials-file: $credPath
no-autoupdate: true
ingress:
  - hostname: $Hostname
    service: http://127.0.0.1:$Port
  - service: http_status:404
"@ | Set-Content -Path $cfgPath -Encoding ASCII
Write-Ok "Ingress config written: $cfgPath"

# --- 4. Create the DNS CNAME route (best-effort; may already exist) ---
Write-Step 'Routing DNS (CNAME)'
$dns = (& $cf tunnel route dns $tunnelName $Hostname 2>&1) -join "`n"
Write-Info $dns
Write-Ok "CNAME $Hostname -> $tunnelId.cfargotunnel.com"

# --- 5. Backup + update hostname-dependent .env values ---
Write-Step 'Updating .env (hostname-dependent values)'
$envFile = Join-Path $root '.env'
$backupFile = Join-Path $tunnelDir 'env.backup.json'
if (-not (Test-Path $backupFile)) {
    $g = { param($k) $m = Select-String -Path $envFile -Pattern "^$k="; if ($m) { $m.Line } else { "$k=" } }
    $orig = [ordered]@{
        APP_URL                = & $g 'APP_URL'
        SESSION_DOMAIN         = & $g 'SESSION_DOMAIN'
        SESSION_SECURE_COOKIE  = & $g 'SESSION_SECURE_COOKIE'
        GOOGLE_REDIRECT_URI    = & $g 'GOOGLE_REDIRECT_URI'
    }
    $orig | ConvertTo-Json | Set-Content -Path $backupFile -Encoding UTF8
}
function Set-EnvLine([string]$key, [string]$value) {
    $lines = Get-Content $envFile
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^$key=") { $lines[$i] = "$key=$value"; $found = $true; break }
    }
    if (-not $found) { $lines += "$key=$value" }
    Set-Content -Path $envFile -Value $lines -Encoding ASCII
}
$publicUrl = "https://$Hostname"
Set-EnvLine 'APP_URL'               $publicUrl
Set-EnvLine 'SESSION_DOMAIN'        ".$Zone"
Set-EnvLine 'SESSION_SECURE_COOKIE' 'true'
Set-EnvLine 'GOOGLE_REDIRECT_URI'   "$publicUrl/auth/google/callback"

Push-Location $root
& $phpPath artisan config:clear 2>&1 | Out-Null
& $phpPath artisan config:cache 2>&1 | Out-Null
& $phpPath artisan view:cache   2>&1 | Out-Null
Pop-Location
Write-Ok 'Config + view re-cached with new hostname'
# --- 6. Start Laravel server (if not already on this port) ---
Write-Step 'Starting Laravel server'
if (-not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
    $srvProc = Start-Process -FilePath $phpPath -ArgumentList 'artisan','serve',"--host=0.0.0.0","--port=$Port",'--no-reload' `
        -WorkingDirectory $root -WindowStyle Minimized -PassThru
    $srvProc.Id | Set-Content (Join-Path $demoDir 'serve.pid')
} else { Write-Info "Port $Port already listening - reusing existing server" }
Write-Ok 'Laravel serve (single worker) on :8000'

# --- 7. Optionally boot Python service + queue workers ---
if ($StartPythonQueue) {
    Write-Step 'Starting Python service + 3 queue workers'
    if (-not (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath 'python' -ArgumentList 'Model\server.py' -WorkingDirectory $root -WindowStyle Minimized -PassThru |
            ForEach-Object { $_.Id | Set-Content (Join-Path $demoDir 'python.pid') }
    } else { Write-Info 'Python service already on :5000' }
    for ($i = 1; $i -le 3; $i++) {
        Start-Process -FilePath $phpPath -ArgumentList 'artisan','queue:work','--tries=3','--timeout=900','--sleep=1' `
            -WorkingDirectory $root -WindowStyle Minimized -PassThru |
            ForEach-Object { $_.Id | Add-Content (Join-Path $demoDir 'queue.pid') }
    }
    Write-Ok 'Python + workers started'
}

# --- 8. Run the named tunnel ---
Write-Step 'Starting named tunnel'
$outLog = Join-Path $tunnelDir 'tunnel.out.log'
$errLog = Join-Path $tunnelDir 'tunnel.err.log'
$tunnelProc = Start-Process -FilePath $cf `
    -ArgumentList 'tunnel','--config',$cfgPath,'run',"--name=$tunnelName",'--no-autoupdate' `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
$tunnelProc.Id | Set-Content (Join-Path $tunnelDir 'tunnel.pid')

Start-Sleep -Seconds 6
$ok = $false
try { $ok = ((Invoke-WebRequest -Uri "$publicUrl/up" -TimeoutSec 15 -UseBasicParsing).StatusCode -eq 200) } catch { $ok = $false }
if ($ok) {
    Write-Host ''
    Write-Host ('=' * 60) -ForegroundColor Yellow
    Write-Host '  STABLE DEPLOY READY (PUBLIC)' -ForegroundColor Yellow
    Write-Host "  URL      : $publicUrl" -ForegroundColor Yellow
    Write-Host '  Logins   : stable (hostname no longer rotates)' -ForegroundColor Yellow
    Write-Host '  Google   : authorize this redirect URI in the Google OAuth console:' -ForegroundColor Yellow
    Write-Host "             $publicUrl/auth/google/callback" -ForegroundColor Yellow
    Write-Host '  Remove   : .\undeploy-named-tunnel.ps1 -Hostname ' $Hostname -ForegroundColor Yellow
    Write-Host ('=' * 60) -ForegroundColor Yellow
    Write-Host ''
} else {
    Write-Bad "Could not reach $publicUrl/up yet. Check $errLog"
    Write-Info 'Tunnel runs as a background process; first DNS propagation may take a few seconds.'
}