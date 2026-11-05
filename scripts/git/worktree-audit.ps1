[CmdletBinding()]
param(
    [string]$RepoPath = (Get-Location).Path,
    [string]$BaseRef = "main",
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Invoke-GitText {
    param(
        [Parameter(Mandatory = $true)][string[]]$GitArgs,
        [string]$WorkingDirectory = $RepoPath,
        [switch]$AllowFailure
    )
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = @(& git -C $WorkingDirectory @GitArgs 2>&1)
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "git -C $WorkingDirectory $($GitArgs -join ' ') failed with exit $code"
    }
    return [pscustomobject]@{ Output = $output; ExitCode = $code }
}

try {
    $topLevel = (Invoke-GitText -GitArgs @("rev-parse", "--show-toplevel")).Output | Select-Object -First 1
    if (-not $topLevel) {
        throw "RepoPath is not a Git worktree: $RepoPath"
    }
    $RepoPath = (Resolve-Path -LiteralPath $topLevel).Path
    $raw = @((Invoke-GitText -GitArgs @("worktree", "list", "--porcelain")).Output)
    $records = @()
    $current = $null
    foreach ($line in $raw + @("")) {
        if (-not $line) {
            if ($null -ne $current) {
                $records += [pscustomobject]$current
                $current = $null
            }
            continue
        }
        if ($line.StartsWith("worktree ")) {
            if ($null -ne $current) {
                $records += [pscustomobject]$current
            }
            $current = [ordered]@{
                Path = $line.Substring(9)
                HEAD = $null
                Branch = "(detached)"
                Bare = $false
                Detached = $false
                Exists = $false
                DirtyCount = $null
                Ahead = $null
                Behind = $null
                BaseRef = $BaseRef
                ProtectedFromAutomaticRemoval = $true
            }
        } elseif ($null -ne $current) {
            if ($line.StartsWith("HEAD ")) {
                $current.HEAD = $line.Substring(5)
            } elseif ($line.StartsWith("branch ")) {
                $current.Branch = $line.Substring(7) -replace "^refs/heads/", ""
            } elseif ($line -eq "bare") {
                $current.Bare = $true
            } elseif ($line -eq "detached") {
                $current.Detached = $true
            }
        }
    }

    foreach ($record in $records) {
        $record.Exists = Test-Path -LiteralPath $record.Path -PathType Container
        if (-not $record.Exists) {
            continue
        }
        $record.DirtyCount = @(& git -C $record.Path status --porcelain=v1 2>$null).Count
        $baseCheck = Invoke-GitText -GitArgs @("rev-parse", "--verify", $BaseRef) -WorkingDirectory $record.Path -AllowFailure
        if ($baseCheck.ExitCode -eq 0) {
            $counts = ((Invoke-GitText -GitArgs @("rev-list", "--left-right", "--count", "$BaseRef...HEAD") -WorkingDirectory $record.Path).Output | Select-Object -First 1)
            if ($counts -match "^(\d+)\s+(\d+)$") {
                $record.Behind = [int]$Matches[1]
                $record.Ahead = [int]$Matches[2]
            }
        }
    }

    $result = [ordered]@{
        GeneratedAt = (Get-Date).ToUniversalTime().ToString("o")
        RepoPath = $RepoPath
        BaseRef = $BaseRef
        WorktreeCount = $records.Count
        AutomaticRemovalPerformed = $false
        Worktrees = $records
    }
    if ($Json) {
        $result | ConvertTo-Json -Depth 8
    } else {
        Write-Output "Worktree audit (read-only)"
        Write-Output "Base ref: $BaseRef"
        foreach ($record in $records) {
            if (-not $record.Exists) {
                Write-Output "  - MISSING | $($record.Path)"
                continue
            }
            $divergence = if ($null -eq $record.Ahead) { "ahead=UNKNOWN behind=UNKNOWN" } else { "ahead=$($record.Ahead) behind=$($record.Behind)" }
            Write-Output "  - $($record.Branch) | dirty=$($record.DirtyCount) | $divergence | $($record.Path)"
        }
        Write-Output "No worktree was removed or modified."
    }
} catch {
    Write-Error $_
    exit 1
}
