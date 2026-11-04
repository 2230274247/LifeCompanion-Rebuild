param(
    [string]$Candidate = (Get-Location).Path,
    [string]$Target
)
$ErrorActionPreference = "Stop"
$guardArgs = @((Join-Path $PSScriptRoot "verify_rebuild_workspace.py"), "--candidate", $Candidate)
if ($Target) { $guardArgs += @("--target", $Target) }
& python @guardArgs
if ($LASTEXITCODE -ne 0) { throw "Rebuild workspace guard rejected this operation." }
