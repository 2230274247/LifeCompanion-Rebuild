$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root "infra\runtime\public"
$exe = Join-Path $runtime "cpolar.exe"
$config = Join-Path $runtime "cpolar.yml"
$task = Get-ScheduledTask -TaskName "ShiguangPublicTunnel" -ErrorAction SilentlyContinue
if ($task) {
    try { Stop-ScheduledTask -TaskName "ShiguangPublicTunnel" } catch { }
    Unregister-ScheduledTask -TaskName "ShiguangPublicTunnel" -Confirm:$false
}
Get-CimInstance Win32_Process -Filter "Name = 'cpolar.exe'" |
    Where-Object { $_.ExecutablePath -eq $exe -and $_.CommandLine.Contains($config) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId }
$urlFile = Join-Path $runtime "public-url.txt"
if (Test-Path -LiteralPath $urlFile) { Remove-Item -LiteralPath $urlFile }
Write-Host "Shiguang public access stopped. Local services remain running." -ForegroundColor Green
