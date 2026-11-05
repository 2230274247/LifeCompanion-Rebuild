[CmdletBinding()]
param(
    [string]$RepoPath = (Get-Location).Path,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Invoke-GitText {
    param(
        [Parameter(Mandatory = $true)][string[]]$GitArgs
    )
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = @(& git -C $RepoPath @GitArgs 2>&1)
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($code -ne 0) {
        throw "git $($GitArgs -join ' ') failed: $($output -join ' ')"
    }
    return $output
}

function Get-DirtyKind {
    param([string]$RelativePath)
    $normalized = $RelativePath -replace "\\", "/"
    if ($normalized -match "(^|/)(node_modules|\.venv|__pycache__|\.pytest_cache|dist|coverage|\.turbo)(/|$)") {
        return "generated"
    }
    if ($normalized -match "(^|/)\.env($|\.)" -and $normalized -notmatch "\.env\.example$") {
        return "sensitive"
    }
    if ($normalized -match "(^|/)(uploads|runtime|volumes|data)(/|$)" -or
        $normalized -match "\.(sqlite3?|db|archive|dump|pem|pfx|p12|key)$") {
        return "stateful"
    }
    if ($normalized -match "^evidence/") {
        return "evidence"
    }
    if ($normalized -match "^docs/|\.md$|^README") {
        return "docs"
    }
    if ($normalized -match "(^tests?/|^scripts/|/tests?/|\.spec\.|\.test\.|_test\.)") {
        return "test"
    }
    if ($normalized -match "^(services|apps|infra|fixtures|patches)/") {
        return "source"
    }
    return "other"
}

try {
    $topLevel = (Invoke-GitText -GitArgs @("rev-parse", "--show-toplevel")).Trim()
    if (-not $topLevel) {
        throw "RepoPath is not a Git worktree: $RepoPath"
    }
    $RepoPath = (Resolve-Path -LiteralPath $topLevel).Path

    $branch = (Invoke-GitText -GitArgs @("branch", "--show-current")).Trim()
    if (-not $branch) {
        $branch = "(detached)"
    }
    $head = (Invoke-GitText -GitArgs @("rev-parse", "HEAD")).Trim()
    $remoteLines = @(Invoke-GitText -GitArgs @("remote", "-v") | Where-Object { $_.Trim() })
    $statusLines = @(Invoke-GitText -GitArgs @("status", "--porcelain=v1"))
    $dirty = @()
    foreach ($line in $statusLines) {
        if (-not $line -or $line.Length -lt 4) {
            continue
        }
        $code = $line.Substring(0, 2)
        $path = $line.Substring(3)
        if ($path -match " -> ") {
            $path = ($path -split " -> ")[-1]
        }
        $dirty += [pscustomobject]@{
            Status = $code
            Path = $path
            Kind = Get-DirtyKind -RelativePath $path
            Unmerged = ($code -match "^(DD|AU|UD|UA|DU|AA|UU)$")
        }
    }

    $worktreeLines = @(Invoke-GitText -GitArgs @("worktree", "list", "--porcelain"))
    $worktrees = @()
    $current = $null
    foreach ($line in $worktreeLines + @("")) {
        if (-not $line) {
            if ($null -ne $current) {
                $worktrees += [pscustomobject]$current
                $current = $null
            }
            continue
        }
        if ($line.StartsWith("worktree ")) {
            if ($null -ne $current) {
                $worktrees += [pscustomobject]$current
            }
            $current = [ordered]@{
                Path = $line.Substring(9)
                HEAD = $null
                Branch = $null
                Detached = $false
                DirtyCount = $null
                Exists = $false
            }
        } elseif ($null -ne $current) {
            if ($line.StartsWith("HEAD ")) {
                $current.HEAD = $line.Substring(5)
            } elseif ($line.StartsWith("branch ")) {
                $current.Branch = $line.Substring(7) -replace "^refs/heads/", ""
            } elseif ($line -eq "detached") {
                $current.Detached = $true
            }
        }
    }
    foreach ($worktree in $worktrees) {
        $worktree.Exists = Test-Path -LiteralPath $worktree.Path -PathType Container
        if ($worktree.Exists) {
            $worktree.DirtyCount = @(& git -C $worktree.Path status --porcelain=v1 2>$null).Count
        }
    }

    $nested = @()
    $productsDir = Join-Path $RepoPath "products"
    if (Test-Path -LiteralPath $productsDir -PathType Container) {
        foreach ($child in Get-ChildItem -LiteralPath $productsDir -Directory -Force) {
            if (-not (Test-Path -LiteralPath (Join-Path $child.FullName ".git"))) {
                continue
            }
            $nestedDirty = @(& git -C $child.FullName status --porcelain=v1 2>$null)
            $nestedHead = (& git -C $child.FullName rev-parse HEAD 2>$null | Select-Object -First 1)
            $nestedBranch = (& git -C $child.FullName branch --show-current 2>$null | Select-Object -First 1)
            $nestedRemote = @(& git -C $child.FullName remote -v 2>$null | Where-Object { $_.Trim() })
            $nested += [pscustomobject]@{
                Path = $child.FullName
                Branch = if ($nestedBranch) { $nestedBranch } else { "(detached)" }
                HEAD = $nestedHead
                DirtyCount = $nestedDirty.Count
                RemoteCount = $nestedRemote.Count
            }
        }
    }

    $result = [ordered]@{
        GeneratedAt = (Get-Date).ToUniversalTime().ToString("o")
        RepoPath = $RepoPath
        Branch = $branch
        HEAD = $head
        RemoteCount = $remoteLines.Count
        RemoteStatus = if ($remoteLines.Count -gt 0) { "REMOTE_CONFIGURED" } else { "PUSH_BLOCKED_NO_REMOTE" }
        DirtyCount = $dirty.Count
        UnmergedCount = @($dirty | Where-Object { $_.Unmerged }).Count
        DirtyByKind = @($dirty | Group-Object Kind | ForEach-Object {
            [pscustomobject]@{ Kind = $_.Name; Count = $_.Count }
        })
        DirtyFiles = $dirty
        Worktrees = $worktrees
        NestedRepositories = $nested
    }

    if ($Json) {
        $result | ConvertTo-Json -Depth 8
    } else {
        Write-Output "Git workspace inspection"
        Write-Output "Branch:        $branch"
        Write-Output "HEAD:          $head"
        Write-Output "Dirty files:   $($dirty.Count)"
        Write-Output "Unmerged:      $($result.UnmergedCount)"
        Write-Output "Remote status: $($result.RemoteStatus)"
        Write-Output "Worktrees:"
        foreach ($worktree in $worktrees) {
            $state = if ($worktree.Exists) { "dirty=$($worktree.DirtyCount)" } else { "MISSING" }
            Write-Output "  - $($worktree.Branch) | $($worktree.HEAD) | $state | $($worktree.Path)"
        }
        if ($dirty.Count -gt 0) {
            Write-Output "Dirty classification:"
            foreach ($group in ($dirty | Group-Object Kind)) {
                Write-Output "  - $($group.Name): $($group.Count)"
            }
        }
        if ($nested.Count -gt 0) {
            Write-Output "Nested repositories:"
            foreach ($item in $nested) {
                Write-Output "  - $($item.Branch) | dirty=$($item.DirtyCount) | remotes=$($item.RemoteCount) | $($item.Path)"
            }
        }
    }
} catch {
    Write-Error $_
    exit 1
}
