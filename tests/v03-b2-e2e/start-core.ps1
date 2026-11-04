param(
    [Parameter(Mandatory = $true)]
    [string]$RuntimeDir,
    [string]$Python = "",
    [string]$ChatUrl = "http://127.0.0.1:3093",
    [switch]$DisableAutomaticImageGeneration
)

$ErrorActionPreference = "Stop"
$rebuildRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$runtime = [System.IO.Path]::GetFullPath($RuntimeDir)
$envFiles = @(
    (Join-Path $rebuildRoot "infra\runtime\p00\acceptance.env"),
    "H:\AI For research institute\LifeCompanion-Rebuild\infra\.env",
    "H:\AI For research institute\LifeCompanion-Rebuild\tests\v03-b0-kolors\.env.local"
)
foreach ($envFile in $envFiles) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if (
            $line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$' -and
            -not [string]::IsNullOrWhiteSpace($Matches[2]) -and
            [string]::IsNullOrWhiteSpace(
                [Environment]::GetEnvironmentVariable($Matches[1], "Process")
            )
        ) {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
        }
    }
}

if (-not $Python) {
    $Python = Join-Path $rebuildRoot "infra\runtime\p02\venv\Scripts\python.exe"
}

$env:PYTHONPATH = Join-Path $rebuildRoot "services\life-core"
$env:LIFE_DATABASE_PATH = Join-Path $runtime "b2.sqlite3"
$env:LIFE_MOMENT_MEDIA_ROOT = Join-Path $runtime "moment-media"
$env:LIFE_MEMOS_TOKENS_FILE = Join-Path $runtime "memos-tokens.json"
$env:LIFE_HOST = "127.0.0.1"
$env:LIFE_PORT = "8032"
$env:LIFE_LIBRECHAT_BASE_URL = $ChatUrl
$env:LIFE_ALLOWED_ORIGINS = "http://127.0.0.1:4182"
$env:MEMORY_LLM_REQUEST_BUDGET = "3"
$env:LIFE_MOMENT_SCORING_REQUEST_BUDGET = "1"
$env:LIFE_MOMENT_PROMPT_REQUEST_BUDGET = "1"
$env:LIFE_MOMENT_IMAGE_REQUEST_BUDGET = "1"
$env:LIFE_MOMENT_WINDOWS_V03 = "true"
$env:LIFE_MOMENT_IMAGE_GENERATION_ENABLED = if (
    $DisableAutomaticImageGeneration
) { "false" } else { "true" }
$env:LIFE_MOMENT_WORKERS_ENABLED = "true"
$env:LIFE_MOMENT_SCHEDULER_EXTERNAL = "false"
$env:LIFE_MOMENT_IMAGE_PROVIDER = "kolors"
$env:LIFE_MOMENT_IMAGE_MODEL = "Kwai-Kolors/Kolors"
$env:LIFE_DIRECT_MOMENT_TEST_ENABLED = "true"
$env:LIFE_DIRECT_MOMENT_TEST_USERNAME = "test"
$env:LIFE_DIRECT_MOMENT_TEST_UNLIMITED = "true"
$env:IMAGE_PROVIDER_ALLOW_GENERIC_BINARY_MIME = "true"

Set-Location -LiteralPath (Join-Path $rebuildRoot "services\life-core")
& $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8032
