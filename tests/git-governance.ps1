[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$inspectScript = Join-Path $root "scripts/git/inspect-workspace.ps1"
$checkpointScript = Join-Path $root "scripts/git/checkpoint.ps1"
$auditScript = Join-Path $root "scripts/git/worktree-audit.ps1"
$created = 0
$passed = 0
$failed = 0
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("lifecompanion-git-governance-" + [guid]::NewGuid().ToString("N"))
$powerShellExe = (Get-Process -Id $PID).Path

function Assert-True {
    param([bool]$Condition, [string]$Name, [string]$Detail = "")
    if (-not $Condition) {
        throw "$Name failed. $Detail"
    }
    $script:passed++
    Write-Output "PASS $Name"
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string[]]$GitArgs,
        [switch]$AllowFailure
    )
    $output = @(& git -C $WorkingDirectory @GitArgs 2>&1)
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "git $($GitArgs -join ' ') failed: $($output -join ' ')"
    }
    return [pscustomobject]@{ Output = $output; ExitCode = $code }
}

function Invoke-Tool {
    param(
        [Parameter(Mandatory = $true)][string]$Script,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = @(& $powerShellExe -NoProfile -ExecutionPolicy Bypass -File $Script @Arguments 2>&1)
        return [pscustomobject]@{ Output = $output; ExitCode = $LASTEXITCODE }
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Convert-OutputJson {
    param([string[]]$Output)
    $text = $Output -join "`n"
    $start = $text.IndexOf("{")
    if ($start -lt 0) {
        throw "No JSON object in output: $text"
    }
    return ($text.Substring($start) | ConvertFrom-Json)
}

function New-TestRepository {
    param([string]$Path)
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    Invoke-Git -WorkingDirectory $Path -GitArgs @("init", "-q") | Out-Null
    Invoke-Git -WorkingDirectory $Path -GitArgs @("config", "user.name", "Governance Test") | Out-Null
    Invoke-Git -WorkingDirectory $Path -GitArgs @("config", "user.email", "governance@example.invalid") | Out-Null
    Invoke-Git -WorkingDirectory $Path -GitArgs @("config", "core.autocrlf", "false") | Out-Null
    Invoke-Git -WorkingDirectory $Path -GitArgs @("config", "core.safecrlf", "false") | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $Path "src") -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $Path "src/app.ps1") -Value 'Write-Output "initial"' -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $Path "README.md") -Value "# Test repository" -Encoding UTF8
    Invoke-Git -WorkingDirectory $Path -GitArgs @("add", "src/app.ps1", "README.md") | Out-Null
    Invoke-Git -WorkingDirectory $Path -GitArgs @("commit", "-q", "-m", "chore: initial fixture") | Out-Null
    Invoke-Git -WorkingDirectory $Path -GitArgs @("branch", "-M", "main") | Out-Null
}

try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $repo = Join-Path $tempRoot "repo"
    New-TestRepository -Path $repo

    # 1. Dirty source is reported and preserved.
    Set-Content -LiteralPath (Join-Path $repo "src/app.ps1") -Value 'Write-Output "dirty-preserved"' -Encoding UTF8
    $inspect = Invoke-Tool -Script $inspectScript -Arguments @("-RepoPath", $repo, "-Json")
    Assert-True ($inspect.ExitCode -eq 0) "inspect workspace succeeds"
    $inspectJson = Convert-OutputJson -Output $inspect.Output
    Assert-True ($inspectJson.DirtyCount -ge 1) "dirty source is reported"
    Assert-True ((Get-Content -LiteralPath (Join-Path $repo "src/app.ps1") -Raw) -match "dirty-preserved") "dirty source is not overwritten"

    # 2. .env is refused and remains untracked.
    Set-Content -LiteralPath (Join-Path $repo ".env") -Value "DEMO_API_KEY=not-a-real-secret" -Encoding UTF8
    $beforeSecretCommit = ((Invoke-Git -WorkingDirectory $repo -GitArgs @("rev-list", "--count", "HEAD")).Output | Select-Object -First 1)
    $secretCheckpoint = Invoke-Tool -Script $checkpointScript -Arguments @(
        "-RepoPath", $repo, "-Message", "test: must reject env", "-Path", ".env", "-Json"
    )
    Assert-True ($secretCheckpoint.ExitCode -ne 0) "sensitive .env is refused"
    $afterSecretCommit = ((Invoke-Git -WorkingDirectory $repo -GitArgs @("rev-list", "--count", "HEAD")).Output | Select-Object -First 1)
    Assert-True ($beforeSecretCommit -eq $afterSecretCommit) "refused .env creates no commit"
    $trackedEnv = @((Invoke-Git -WorkingDirectory $repo -GitArgs @("ls-files", ".env")).Output | Where-Object { $_ })
    Assert-True ($trackedEnv.Count -eq 0) "refused .env remains untracked"
    Assert-True (Test-Path -LiteralPath (Join-Path $repo ".env")) "refused .env is not deleted"

    # 3. A normal explicit source checkpoint commits without a remote.
    Set-Content -LiteralPath (Join-Path $repo "src/app.ps1") -Value 'Write-Output "committed-change"' -Encoding UTF8
    $normal = Invoke-Tool -Script $checkpointScript -Arguments @(
        "-RepoPath", $repo, "-Message", "test: commit explicit source", "-Path", "src/app.ps1", "-Json"
    )
    Assert-True ($normal.ExitCode -eq 0) "normal source checkpoint commits"
    $normalJson = Convert-OutputJson -Output $normal.Output
    Assert-True ($normalJson.RemoteStatus -ne "REMOTE_EXISTS") "local commit does not require a remote"
    Assert-True ($normalJson.PushStatus -eq "PUSH_BLOCKED_NO_REMOTE") "no remote is reported explicitly"
    Assert-True ($normalJson.CommitSHA -match "^[0-9a-f]{40}$") "checkpoint reports commit SHA"

    # 4. Repeated checkpoint does not create an empty duplicate commit.
    $countBeforeRepeat = ((Invoke-Git -WorkingDirectory $repo -GitArgs @("rev-list", "--count", "HEAD")).Output | Select-Object -First 1)
    $repeat = Invoke-Tool -Script $checkpointScript -Arguments @(
        "-RepoPath", $repo, "-Message", "test: duplicate", "-Path", "src/app.ps1", "-Json"
    )
    $countAfterRepeat = ((Invoke-Git -WorkingDirectory $repo -GitArgs @("rev-list", "--count", "HEAD")).Output | Select-Object -First 1)
    Assert-True ($repeat.ExitCode -eq 2) "repeat checkpoint reports no changes"
    Assert-True ($countBeforeRepeat -eq $countAfterRepeat) "repeat checkpoint creates no duplicate commit"

    # 5. Worktree audit reports an unmerged branch and never removes it.
    $linked = Join-Path $tempRoot "linked-worktree"
    Invoke-Git -WorkingDirectory $repo -GitArgs @("worktree", "add", "-q", "-b", "feature-unmerged", $linked) | Out-Null
    Set-Content -LiteralPath (Join-Path $linked "src/app.ps1") -Value 'Write-Output "feature-version"' -Encoding UTF8
    Invoke-Git -WorkingDirectory $linked -GitArgs @("add", "src/app.ps1") | Out-Null
    Invoke-Git -WorkingDirectory $linked -GitArgs @("commit", "-q", "-m", "feat: unmerged fixture") | Out-Null
    $audit = Invoke-Tool -Script $auditScript -Arguments @("-RepoPath", $repo, "-BaseRef", "main", "-Json")
    Assert-True ($audit.ExitCode -eq 0) "worktree audit succeeds"
    $auditJson = Convert-OutputJson -Output $audit.Output
    $linkedRecord = @($auditJson.Worktrees | Where-Object {
        ([IO.Path]::GetFullPath($_.Path)).TrimEnd("\") -eq ([IO.Path]::GetFullPath($linked)).TrimEnd("\")
    }) | Select-Object -First 1
    Assert-True ($null -ne $linkedRecord) "unmerged worktree is reported"
    Assert-True ($linkedRecord.Ahead -ge 1) "worktree ahead count is reported"
    Assert-True ($auditJson.AutomaticRemovalPerformed -eq $false) "worktree audit performs no removal"
    Assert-True (Test-Path -LiteralPath $linked) "unmerged worktree still exists"

    # 6. A conflict blocks checkpoint and preserves both sides.
    Set-Content -LiteralPath (Join-Path $repo "src/app.ps1") -Value 'Write-Output "main-version"' -Encoding UTF8
    Invoke-Git -WorkingDirectory $repo -GitArgs @("add", "src/app.ps1") | Out-Null
    Invoke-Git -WorkingDirectory $repo -GitArgs @("commit", "-q", "-m", "test: main conflict side") | Out-Null
    $merge = Invoke-Git -WorkingDirectory $repo -GitArgs @("merge", "feature-unmerged") -AllowFailure
    Assert-True ($merge.ExitCode -ne 0) "fixture merge produces a conflict"
    $conflictCheckpoint = Invoke-Tool -Script $checkpointScript -Arguments @(
        "-RepoPath", $repo, "-Message", "test: must block conflict", "-Path", "src/app.ps1", "-Json"
    )
    Assert-True ($conflictCheckpoint.ExitCode -ne 0) "checkpoint refuses unresolved conflict"
    $conflictText = Get-Content -LiteralPath (Join-Path $repo "src/app.ps1") -Raw
    Assert-True ($conflictText -match "main-version" -and $conflictText -match "feature-version") "conflict preserves both sides"
    Assert-True ($conflictText -match "<<<<<<<" -and $conflictText -match ">>>>>>>") "conflict markers remain for explicit resolution"

    # 7. Post-conflict inspection reports an unmerged status.
    $finalInspect = Invoke-Tool -Script $inspectScript -Arguments @("-RepoPath", $repo, "-Json")
    $finalJson = Convert-OutputJson -Output $finalInspect.Output
    Assert-True ($finalInspect.ExitCode -eq 0) "inspection remains read-only during conflict"
    Assert-True ($finalJson.UnmergedCount -ge 1) "inspection reports unresolved conflict"

    Write-Output ""
    Write-Output "Git governance tests: $passed passed, $failed failed"
} catch {
    $failed++
    Write-Error $_
} finally {
    if (Test-Path -LiteralPath $tempRoot) {
        $resolvedTemp = (Resolve-Path -LiteralPath $tempRoot).Path
        $tempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd("\") + "\"
        if ($resolvedTemp.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force -ErrorAction SilentlyContinue
        } else {
            Write-Error "Refusing to remove unexpected test path: $resolvedTemp"
        }
    }
}

if ($failed -gt 0) {
    exit 1
}
exit 0
