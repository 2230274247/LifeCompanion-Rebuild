[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Message,
    [Parameter(Mandatory = $true)][string[]]$Path,
    [string]$RepoPath = (Get-Location).Path,
    [switch]$DryRun,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
$MaxFileBytes = 10MB

function Invoke-GitText {
    param(
        [Parameter(Mandatory = $true)][string[]]$GitArgs,
        [switch]$AllowFailure
    )
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = @(& git -C $RepoPath @GitArgs 2>&1 | Where-Object {
            "$_" -notmatch "^warning:"
        })
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($code -ne 0 -and -not $AllowFailure) {
        throw "git $($GitArgs -join ' ') failed with exit $code"
    }
    return [pscustomobject]@{ Output = $output; ExitCode = $code }
}

function Test-SensitivePath {
    param([string]$RelativePath)
    $normalized = $RelativePath -replace "\\", "/"
    $leaf = Split-Path -Leaf $normalized
    if ($leaf -eq ".env.example") {
        return $false
    }
    if ($leaf -match "^\.env($|\.)") {
        return $true
    }
    if ($normalized -match "(^|/)(node_modules|\.venv|__pycache__|\.pytest_cache|dist|coverage|\.turbo|\.work)(/|$)") {
        return $true
    }
    if ($normalized -match "(^|/)(uploads|runtime|volumes)(/|$)") {
        return $true
    }
    if ($leaf -match "(?i)^(id_rsa|id_ed25519|credentials\.json|service-account.*\.json|secrets?\.json)$") {
        return $true
    }
    if ($leaf -match "(?i)\.(pem|pfx|p12|key|sqlite|sqlite3|db|archive|dump|bak)$") {
        return $true
    }
    if ($leaf -match "\.log$") {
        return $true
    }
    return $false
}

function Get-RepoRelativePath {
    param([string]$InputPath)
    $full = if ([IO.Path]::IsPathRooted($InputPath)) {
        [IO.Path]::GetFullPath($InputPath)
    } else {
        [IO.Path]::GetFullPath((Join-Path $RepoPath $InputPath))
    }
    $rootWithSeparator = $RepoPath.TrimEnd("\", "/") + [IO.Path]::DirectorySeparatorChar
    if ($full -eq $RepoPath) {
        throw "Refusing to checkpoint the entire repository. Provide explicit paths."
    }
    if (-not $full.StartsWith($rootWithSeparator, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside the repository: $InputPath"
    }
    return $full.Substring($rootWithSeparator.Length) -replace "\\", "/"
}

function Test-SecretContent {
    param([string]$RelativePath, [string]$Content)
    $patterns = @(
        "-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "\b(AKIA|ASIA)[0-9A-Z]{16}\b",
        "\bgh[pousr]_[A-Za-z0-9]{20,}\b",
        "\bsk-[A-Za-z0-9_-]{20,}\b",
        "(?im)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)\s*[:=]\s*[`"']?(?!<|your[-_]|example|placeholder|redacted|change[-_]?me|\$\{|x{4,})[A-Za-z0-9_./+=-]{20,}"
    )
    foreach ($pattern in $patterns) {
        if ($Content -match $pattern) {
            return $true
        }
    }
    return $false
}

try {
    if (-not $Message.Trim()) {
        throw "Commit message must not be empty."
    }
    $topLevel = (Invoke-GitText -GitArgs @("rev-parse", "--show-toplevel")).Output | Select-Object -First 1
    if (-not $topLevel) {
        throw "RepoPath is not a Git worktree: $RepoPath"
    }
    $RepoPath = (Resolve-Path -LiteralPath $topLevel).Path

    $stagedBefore = @((Invoke-GitText -GitArgs @("diff", "--cached", "--name-only")).Output | Where-Object { $_ })
    if ($stagedBefore.Count -gt 0) {
        throw "The index already contains staged files. Commit or unstage them explicitly before using checkpoint.ps1."
    }
    $unmerged = @((Invoke-GitText -GitArgs @("diff", "--name-only", "--diff-filter=U")).Output | Where-Object { $_ })
    if ($unmerged.Count -gt 0) {
        throw "Unresolved merge conflicts prevent a safe checkpoint: $($unmerged -join ', ')"
    }

    $expandedPaths = @()
    foreach ($rawPath in $Path) {
        $expandedPaths += @($rawPath -split "\s*,\s*" | Where-Object { $_ })
    }
    $relativePaths = @()
    foreach ($item in $expandedPaths) {
        $candidatePath = if ([IO.Path]::IsPathRooted($item)) {
            [IO.Path]::GetFullPath($item)
        } else {
            [IO.Path]::GetFullPath((Join-Path $RepoPath $item))
        }
        if (-not (Test-Path -LiteralPath $candidatePath)) {
            throw "Path does not exist: $item"
        }
        $relative = Get-RepoRelativePath -InputPath $item
        if (Test-SensitivePath -RelativePath $relative) {
            throw "Refusing to commit sensitive or generated path: $relative"
        }
        $relativePaths += $relative
    }
    $relativePaths = @($relativePaths | Select-Object -Unique)

    $candidateOutput = @((Invoke-GitText -GitArgs (@("ls-files", "--others", "--cached", "--exclude-standard", "--") + $relativePaths)).Output | Where-Object { $_ })
    foreach ($candidate in $candidateOutput) {
        if (Test-SensitivePath -RelativePath $candidate) {
            throw "Refusing to commit sensitive or generated path: $candidate"
        }
        $absolute = Join-Path $RepoPath $candidate
        if (Test-Path -LiteralPath $absolute -PathType Leaf) {
            $length = (Get-Item -LiteralPath $absolute).Length
            if ($length -gt $MaxFileBytes) {
                throw "Refusing oversized file ($length bytes): $candidate"
            }
        }
    }

    if ($DryRun) {
        $dryResult = [ordered]@{
            Status = "DRY_RUN_VALID"
            RepoPath = $RepoPath
            Paths = $relativePaths
            CandidateCount = $candidateOutput.Count
        }
        if ($Json) { $dryResult | ConvertTo-Json -Depth 6 }
        else { $dryResult | Format-List }
        exit 0
    }

    $addResult = Invoke-GitText -GitArgs (@("add", "--") + $relativePaths)
    if ($addResult.ExitCode -ne 0) {
        throw "git add failed with exit $($addResult.ExitCode)"
    }
    $staged = @((Invoke-GitText -GitArgs @("diff", "--cached", "--name-only")).Output | Where-Object { $_ })
    if ($staged.Count -eq 0) {
        $emptyResult = [ordered]@{
            Status = "NO_CHANGES"
            Message = "No staged changes after adding the requested paths."
            RepoPath = $RepoPath
            Paths = $relativePaths
        }
        if ($Json) { $emptyResult | ConvertTo-Json -Depth 6 }
        else { Write-Output $emptyResult.Message }
        exit 2
    }

    $textExtensions = @(".md", ".txt", ".json", ".yaml", ".yml", ".ps1", ".py", ".js", ".mjs", ".cjs",
        ".ts", ".tsx", ".jsx", ".css", ".html", ".toml", ".ini", ".cfg", ".sh", ".sql", ".env")
    foreach ($stagedPath in $staged) {
        if (Test-SensitivePath -RelativePath $stagedPath) {
            Invoke-GitText -GitArgs (@("restore", "--staged", "--") + $relativePaths) -AllowFailure | Out-Null
            throw "Refusing to commit sensitive or generated path: $stagedPath"
        }
        $extension = [IO.Path]::GetExtension($stagedPath).ToLowerInvariant()
        if ($textExtensions -notcontains $extension) {
            continue
        }
        $contentResult = Invoke-GitText -GitArgs @("show", ":$stagedPath") -AllowFailure
        if ($contentResult.ExitCode -ne 0) {
            continue
        }
        if (Test-SecretContent -RelativePath $stagedPath -Content ($contentResult.Output -join "`n")) {
            Invoke-GitText -GitArgs (@("restore", "--staged", "--") + $relativePaths) -AllowFailure | Out-Null
            throw "Potential secret detected in staged content: $stagedPath"
        }
    }

    $commitResult = Invoke-GitText -GitArgs @("commit", "-m", $Message) -AllowFailure
    if ($commitResult.ExitCode -ne 0) {
        throw "git commit failed with exit $($commitResult.ExitCode): $($commitResult.Output -join ' ')"
    }
    $sha = ((Invoke-GitText -GitArgs @("rev-parse", "HEAD")).Output | Select-Object -First 1)
    $remoteLines = @((Invoke-GitText -GitArgs @("remote", "-v")).Output | Where-Object { $_.Trim() })
    $remaining = @((Invoke-GitText -GitArgs @("status", "--porcelain=v1")).Output | Where-Object { $_ })
    $result = [ordered]@{
        Status = "LOCAL_COMMITTED"
        RepoPath = $RepoPath
        CommitSHA = $sha
        Message = $Message
        CommitCount = 1
        PushStatus = if ($remoteLines.Count -gt 0) { "REMOTE_CONFIGURED_NOT_PUSHED" } else { "PUSH_BLOCKED_NO_REMOTE" }
        RemainingDirtyFiles = $remaining.Count
        StagedFiles = $staged
    }
    if ($Json) {
        $result | ConvertTo-Json -Depth 6
    } else {
        Write-Output "LOCAL_COMMITTED $sha"
        Write-Output "PUSH_STATUS $($result.PushStatus)"
        Write-Output "Remaining dirty files: $($remaining.Count)"
    }
} catch {
    Write-Error $_
    exit 1
}
