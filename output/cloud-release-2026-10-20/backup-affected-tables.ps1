$ErrorActionPreference = 'Stop'
$settings = @{}
foreach ($line in Get-Content -LiteralPath 'C:\dev\Trilingua\trilingua-code\.env') {
    if ($line -match '^([A-Z0-9_]+)=(.*)$') { $settings[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'") }
}
if ($settings['SUPABASE_URL'].TrimEnd('/') -ne 'https://wetafzmelvwiaerofuvh.supabase.co') { throw 'Unexpected database project; export stopped.' }
if (-not $settings['SUPABASE_SERVICE_ROLE_KEY']) { throw 'Server-side export credential is missing.' }
$headers = @{ apikey=$settings['SUPABASE_SERVICE_ROLE_KEY']; Authorization="Bearer $($settings['SUPABASE_SERVICE_ROLE_KEY'])"; Prefer='count=exact' }
$snapshot = @{ captured_utc=[DateTime]::UtcNow.ToString('o'); project='wetafzmelvwiaerofuvh'; tables=@{} }
foreach ($table in @('translation_history','translation_metrics','migrations')) {
    $response = Invoke-WebRequest -Uri "$($settings['SUPABASE_URL'])/rest/v1/${table}?select=*&order=id&limit=1000" -Headers $headers -TimeoutSec 30
    $rows = @($response.Content | ConvertFrom-Json)
    $count = [int](($response.Headers['Content-Range'] -join '') -split '/')[-1]
    if ($rows.Count -ne $count) { throw "Incomplete export for $table; stopped before migration." }
    $snapshot.tables[$table] = $rows
}
Add-Type -AssemblyName System.Security
$plain = [Text.Encoding]::UTF8.GetBytes(($snapshot | ConvertTo-Json -Depth 100 -Compress))
$protected = [Security.Cryptography.ProtectedData]::Protect($plain,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
$target = Join-Path $PSScriptRoot 'affected-tables-before-migration.dpapi'
[IO.File]::WriteAllBytes($target,$protected)
$restored = [Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($target),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
if ([Convert]::ToBase64String($plain) -ne [Convert]::ToBase64String($restored)) { throw 'Encrypted export verification failed.' }
$verified = [Text.Encoding]::UTF8.GetString($restored) | ConvertFrom-Json
foreach ($table in $snapshot.tables.Keys) {
    if (@($verified.tables.$table).Count -ne @($snapshot.tables[$table]).Count) { throw 'Export row-count verification failed.' }
    Write-Output "$table rows verified: $(@($snapshot.tables[$table]).Count)"
}
Write-Output 'Encrypted affected-table export verified. Does not include Storage object bytes or a full database backup.'
