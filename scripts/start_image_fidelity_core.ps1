param(
    [Parameter(Mandatory = $true)]
    [string]$RuntimeDir,
    [int]$Port = 8034,
    [string]$ChatUrl = "http://127.0.0.1:3093",
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runtime = [System.IO.Path]::GetFullPath($RuntimeDir)
$acceptanceEnv = Join-Path $root "infra\runtime\p00\acceptance.env"

if (-not (Test-Path -LiteralPath $acceptanceEnv)) {
    throw "Missing isolated acceptance environment: $acceptanceEnv"
}
if (-not $Python) {
    $Python = Join-Path $root "infra\runtime\p02\venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing Python runtime: $Python"
}

New-Item -ItemType Directory -Path $runtime -Force | Out-Null
foreach ($line in Get-Content -LiteralPath $acceptanceEnv) {
    if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$' -and $Matches[2]) {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
    }
}

$env:PYTHONPATH = Join-Path $root "services\life-core"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:LIFE_DATABASE_PATH = Join-Path $runtime "life-core.sqlite3"
$env:LIFE_MOMENT_MEDIA_ROOT = Join-Path $runtime "moment-media"
$env:LIFE_MEMOS_TOKENS_FILE = Join-Path $runtime "memos-tokens.json"
$env:LIFE_LIBRECHAT_BASE_URL = $ChatUrl
$env:LIFE_ALLOWED_ORIGINS = "http://127.0.0.1:$Port"
$env:LIFE_MOMENT_WINDOWS_V03 = "true"
$env:LIFE_MOMENT_WORKERS_ENABLED = "false"
$env:LIFE_MOMENT_IMAGE_GENERATION_ENABLED = "false"
$env:LIFE_MOMENT_IMAGE_PROVIDER = "kolors"
$env:LIFE_MOMENT_IMAGE_MODEL = "Kwai-Kolors/Kolors"
$env:LIFE_MOMENT_IMAGE_REQUEST_BUDGET = "1"
$env:LIFE_DIRECT_MOMENT_TEST_ENABLED = "true"
$env:LIFE_DIRECT_MOMENT_TEST_USERNAME = "test"
$env:LIFE_DIRECT_MOMENT_TEST_UNLIMITED = "true"
$env:IMAGE_PROVIDER_ALLOW_GENERIC_BINARY_MIME = "true"

if (-not (Test-Path -LiteralPath $env:LIFE_MEMOS_TOKENS_FILE)) {
    Set-Content -LiteralPath $env:LIFE_MEMOS_TOKENS_FILE -Value "{}" -Encoding utf8NoBOM
}

$process = Start-Process -FilePath $Python `
    -ArgumentList @(
        "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", "$Port"
    ) `
    -WorkingDirectory (Join-Path $root "services\life-core") `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $runtime "core.out.log") `
    -RedirectStandardError (Join-Path $runtime "core.err.log") `
    -PassThru

Set-Content -LiteralPath (Join-Path $runtime "core.pid") `
    -Value $process.Id -Encoding ascii
Write-Output ("PID=" + $process.Id)
Write-Output ("RUNTIME=" + $runtime)
