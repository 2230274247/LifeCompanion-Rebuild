param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][string]$Directory,
    [Parameter(Mandatory=$true)][string]$Program,
    [string[]]$Arguments = @()
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$evidence = Join-Path $root "evidence\v02-memory-reminders"
$started = [DateTimeOffset]::Now.ToString("o")
Push-Location -LiteralPath $Directory
try {
    & $Program @Arguments *> (Join-Path $evidence "$Name.txt")
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
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence "$Name.json") -Encoding utf8
Get-Content -LiteralPath (Join-Path $evidence "$Name.txt") -Tail 15
exit $result
