param(
    [string]$Python = $env:LIFE_PYTHON
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
$env:LIFE_DATABASE_PATH = Join-Path $serviceRoot "data\life-core.sqlite3"
$env:LIFE_HOST = "127.0.0.1"
$env:LIFE_PORT = "8010"

Set-Location -LiteralPath $serviceRoot
& $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8010

