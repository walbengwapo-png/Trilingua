<#
.SYNOPSIS
    Stops all TriLingua demo processes (web, python, queue worker, tunnel).
#>
$ErrorActionPreference = 'SilentlyContinue'

function Stop-PortListener([int]$port, [string]$label) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if ($p -and $p.ProcessName -notin @('System', 'Idle')) {
            Write-Host "Stopping $label (PID $($p.Id) - $($p.ProcessName))" -ForegroundColor Yellow
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host 'Stopping TriLingua demo...' -ForegroundColor Cyan

Stop-PortListener 8000 'Laravel server'
Stop-PortListener 5000  'Python translation server'

# Queue worker/listener: match both supported local launch modes.
Get-CimInstance Win32_Process -Filter "Name='php.exe'" |
    Where-Object { $_.CommandLine -match 'queue:(work|listen)' } |
    ForEach-Object { Write-Host "Stopping queue worker (PID $($_.ProcessId))" -ForegroundColor Yellow; Stop-Process -Id $_.ProcessId -Force }

# Tunnel: cloudflared with --url arg (avoids killing unrelated cloudflared runs)
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
    Where-Object { $_.CommandLine -match '--url' } |
    ForEach-Object { Write-Host "Stopping tunnel (PID $($_.ProcessId))" -ForegroundColor Yellow; Stop-Process -Id $_.ProcessId -Force }

# Stray python running Model\server.py OR its multiprocessing children
# (uvicorn workers survive their parent as orphans and keep port 5000 held)
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'server\.py' -or $_.CommandLine -match 'multiprocessing' } |
    ForEach-Object { Write-Host "Stopping python process (PID $($_.ProcessId))" -ForegroundColor Yellow; Stop-Process -Id $_.ProcessId -Force }

# Clean pid files
Remove-Item "$PSScriptRoot\storage\demo\*.pid" -ErrorAction SilentlyContinue

Write-Host 'All demo processes stopped.' -ForegroundColor Green
