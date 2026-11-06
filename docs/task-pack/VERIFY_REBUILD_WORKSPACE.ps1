# Read-only project identity guard for PowerShell on Windows.
# Usage: powershell -NoProfile -File .\VERIFY_REBUILD_WORKSPACE.ps1 -CandidatePath "H:\AI For research institute\LifeCompanion-Rebuild"
# Exit 0: candidate belongs to exact Rebuild Git repository or its worktree; nonzero: refuse write.
param(
    [string]$CandidatePath = (Get-Location).Path,
    [string]$CanonicalRoot = 'H:\AI For research institute\LifeCompanion-Rebuild'
)
$ErrorActionPreference = 'Stop'
function Fail([string]$why) {
    Write-Error "REBUILD_WORKSPACE_LOCK_FAIL: $why"
    exit 3
}
function Canon([string]$path) {
    return ([System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $path).ProviderPath)).TrimEnd('\','/').ToLowerInvariant()
}
function GitOutput([string]$at, [string[]]$gitArgs) {
    $answer = & git -C $at @gitArgs 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $answer) { Fail "git check failed in $at" }
    return (($answer | Select-Object -First 1).ToString().Trim())
}
function GitCommon([string]$at) {
    $raw = GitOutput $at @('rev-parse','--git-common-dir')
    if (-not [System.IO.Path]::IsPathRooted($raw)) { $raw = Join-Path -Path $at -ChildPath $raw }
    return Canon $raw
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'Git command not found' }
if (-not (Test-Path -LiteralPath $CanonicalRoot -PathType Container)) { Fail 'Canonical Rebuild root absent' }
if (-not (Test-Path -LiteralPath $CandidatePath -PathType Container)) { Fail 'Candidate path absent' }
$main = Canon $CanonicalRoot
$mainTop = Canon (GitOutput $main @('rev-parse','--show-toplevel'))
if ($main -ne $mainTop) { Fail 'Canonical path is not the top-level of the Rebuild Git repository' }
$mainCommon = GitCommon $main
$candidate = Canon $CandidatePath
$candidateTop = Canon (GitOutput $candidate @('rev-parse','--show-toplevel'))
$candidateCommon = GitCommon $candidate
if ($candidateCommon -ne $mainCommon) {
    Fail "Candidate belongs to DIFFERENT Git repository: $candidateTop"
}
# Intentionally does not inspect or print remote URLs (which can contain credentials).
Write-Output "REBUILD_WORKSPACE_LOCK_PASS: $candidateTop"
Write-Output "Git common-dir: $candidateCommon"
exit 0
