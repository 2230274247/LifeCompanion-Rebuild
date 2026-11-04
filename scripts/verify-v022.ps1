param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][string]$Directory,
    [Parameter(Mandatory=$true)][string]$Program,
    [string[]]$Arguments = @()
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$evidence = Join-Path $root "evidence\v022-reminder-dialog"
$started = [DateTimeOffset]::Now.ToString("o")
$attempt = @(Get-ChildItem -LiteralPath $evidence -Filter "$Name-*.json").Count + 1
$stem = "$Name-$attempt"
Push-Location -LiteralPath $Directory
try {
    & $Program @Arguments *> (Join-Path $evidence "$stem.txt")
    $result = $LASTEXITCODE
} finally {
    Pop-Location
}
@{
    started_at = $started
    ended_at = [DateTimeOffset]::Now.ToString("o")
    directory = $Directory
    program = $Program
    arguments = $Arguments
    exit_code = $result
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence "$stem.json") -Encoding utf8
Get-Content -LiteralPath (Join-Path $evidence "$stem.txt") -Tail 16
exit $result
