# Run while the local services are up: powershell -File tests/start-all-restart-check.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$listeners = @(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 5000, 8000 })
if (-not $listeners) { throw 'Start the local services before running this check.' }
$owners = @($listeners.OwningProcess | Sort-Object -Unique)
$launcher = Join-Path $root 'start-all.bat'
if ((Get-Content $launcher -Raw) -match 'Stop-Process|taskkill') {
    throw 'Launcher must not kill running services.'
}
$output = '' | & cmd /d /c "`"$launcher`"" 2>&1
if ($LASTEXITCODE -ne 1 -or ($output -join "`n") -notmatch 'Services are already running') {
    throw "Duplicate startup was not refused: $output"
}
foreach ($owner in $owners) {
    if (-not (Get-Process -Id $owner -ErrorAction SilentlyContinue)) {
        throw "Duplicate startup stopped service process $owner."
    }
}
Write-Output 'PASS: duplicate startup refused; existing services survived.'
