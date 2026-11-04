param(
    [int]$Port = 3001,
    [string]$ChatTarget = $(if ($env:CHAT_TARGET) { $env:CHAT_TARGET } else { "http://127.0.0.1:3080" }),
    [string]$LifeTarget = $(if ($env:LIFE_TARGET) { $env:LIFE_TARGET } else { "http://127.0.0.1:8010" })
)

$ErrorActionPreference = "Stop"
$env:PORT = "$Port"
$env:CHAT_TARGET = $ChatTarget
$env:LIFE_TARGET = $LifeTarget
Set-Location -LiteralPath $PSScriptRoot
node .\server.mjs
