param([switch]$NoBrowser)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root "infra\runtime\public"
$exe = Join-Path $runtime "cpolar.exe"
$config = Join-Path $runtime "cpolar.yml"
$log = Join-Path $runtime "cpolar.log"
$urlFile = Join-Path $runtime "public-url.txt"
$taskName = "ShiguangPublicTunnel"

function Get-PublicUrl {
    if (Test-Path -LiteralPath $log) {
        $text = Get-Content -LiteralPath $log -Raw -ErrorAction SilentlyContinue
        $found = [regex]::Matches([string]$text, 'Tunnel established at (https://[A-Za-z0-9.-]+)')
        if ($found.Count) { return $found[$found.Count - 1].Groups[1].Value }
    }
}

function Test-PublicHealth([string]$Url) {
    if (-not $Url) { return $false }
    try {
        $health = Invoke-RestMethod "$Url/health" -TimeoutSec 10
        return $health.service -eq "life-companion-gateway" -and $health.status -eq "ok"
    } catch {
        return $false
    }
}

foreach ($file in @($exe, $config)) {
    if (-not (Test-Path -LiteralPath $file)) {
        throw "Missing local tunnel setup: $file"
    }
}
& (Join-Path $PSScriptRoot "start-lifecompanion.ps1") -NoBrowser

$running = @(Get-CimInstance Win32_Process -Filter "Name = 'cpolar.exe'" |
    Where-Object { $_.ExecutablePath -eq $exe -and $_.CommandLine.Contains($config) })
$publicUrl = Get-PublicUrl
if (-not ($running.Count -and (Test-PublicHealth $publicUrl))) {
    $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($running.Count -or $existingTask) {
        & (Join-Path $PSScriptRoot "stop-public.ps1")
    }
    if (Test-Path -LiteralPath $urlFile) { Remove-Item -LiteralPath $urlFile }
    if (Test-Path -LiteralPath $log) { Remove-Item -LiteralPath $log }
    $arguments = "http --config `"$config`" --log `"$log`" --log-level INFO --inspect-addr false --proto https 3001"
    $action = New-ScheduledTaskAction -Execute $exe -Argument $arguments -WorkingDirectory $runtime
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
    # No boot/logon trigger: public access starts only when explicitly launched.
    Register-ScheduledTask -TaskName $taskName -Action $action -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $taskName
    Write-Host "Waiting for the HTTPS tunnel..." -ForegroundColor Cyan
    $deadline = (Get-Date).AddSeconds(90)
    $publicUrl = $null
    while ((Get-Date) -lt $deadline) {
        $candidate = Get-PublicUrl
        if (Test-PublicHealth $candidate) {
            $publicUrl = $candidate
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $publicUrl) {
        throw "Public health check failed. Check $log"
    }
}

$publicUrl | Set-Content -LiteralPath $urlFile -Encoding ASCII
Write-Host ""
Write-Host "Shiguang public URL: $publicUrl" -ForegroundColor Green
Write-Host "Saved to: $urlFile"
Write-Host "Keep this computer awake and connected to the Internet."
Write-Host "Closing this window leaves the service running."
Write-Host "Stop public access: scripts\stop-public.ps1"
if (-not $NoBrowser) { Start-Process $publicUrl }
