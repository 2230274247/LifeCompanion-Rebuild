param(
    [string]$Python = $env:LIFE_PYTHON,
    [string]$HostAddress = $(if ($env:LIFE_HOST) { $env:LIFE_HOST } else { "127.0.0.1" }),
    [int]$Port = $(if ($env:LIFE_PORT) { [int]$env:LIFE_PORT } else { 8010 })
)

$ErrorActionPreference = "Stop"
$serviceRoot = $PSScriptRoot
$rebuildRoot = Resolve-Path (Join-Path $serviceRoot "..\..")
$infraEnv = Join-Path $rebuildRoot "infra\.env"
$librechatEnv = Join-Path $rebuildRoot "products\librechat-custom\.env"

foreach ($envFile in @($infraEnv, $librechatEnv)) {
    if (-not (Test-Path -LiteralPath $envFile)) {
        throw "Missing env file: $envFile"
    }
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match '^\s*#|^\s*$|^[^=]+=') {
            continue
        }
    }
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
        }
    }
}

if (-not $Python) {
    $Python = "python"
}

$env:PYTHONPATH = $serviceRoot
if (-not $env:LIFE_DATABASE_PATH) {
    $env:LIFE_DATABASE_PATH = Join-Path $serviceRoot "data\life-core.sqlite3"
}
$env:LIFE_HOST = $HostAddress
$env:LIFE_PORT = "$Port"

Set-Location -LiteralPath $serviceRoot
& $Python -m uvicorn app.main:app --host $HostAddress --port $Port

