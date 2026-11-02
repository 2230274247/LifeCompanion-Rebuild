param(
    [int]$Port = 3001
)

$ErrorActionPreference = "Stop"
$env:PORT = "$Port"
Set-Location -LiteralPath $PSScriptRoot
node .\server.mjs
