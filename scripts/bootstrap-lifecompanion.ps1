param(
    [switch]$SkipFrontendBuild,
    [string]$LibreChatRepository = $env:LIFECOMPANION_LIBRECHAT_REPO
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$parent = Split-Path -Parent $root
$upstream = Join-Path $root "products\librechat-custom"
$patch = Join-Path $root "patches\librechat-v0.8.8-rebuild-p00-p07-20261104.patch"
$baseCommit = "e8f3be08623663d4ad7f7241e693c94469b63bb0"
if (-not $LibreChatRepository) {
    $LibreChatRepository = "https://github.com/LibreChat-AI/LibreChat.git"
}

function Require-Command([string]$Name, [string]$Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "缺少 $Name。$Hint"
    }
}

function Copy-IfMissing([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Destination)) {
        Copy-Item -LiteralPath $Source -Destination $Destination
        Write-Host "[bootstrap] created $Destination"
    } else {
        Write-Host "[bootstrap] kept existing $Destination"
    }
}

function New-HexSecret([int]$ByteLength = 32) {
    $bytes = New-Object byte[] $ByteLength
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    } finally {
        $generator.Dispose()
    }
    return -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

function Initialize-EnvSecret([string]$Path, [string]$Name, [int]$ByteLength = 32) {
    $lines = [System.Collections.Generic.List[string]]::new()
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $lines.Add($line)
    }
    $pattern = '^\s*' + [regex]::Escape($Name) + '=(.*)$'
    $required = $true
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match $pattern) {
            $current = $Matches[1].Trim()
            if ($current -and -not $current.StartsWith("replace-")) {
                $required = $false
            } else {
                $lines[$index] = "$Name=$(New-HexSecret $ByteLength)"
                $required = $false
            }
            break
        }
    }
    if ($required) {
        $lines.Add("$Name=$(New-HexSecret $ByteLength)")
    }
    [System.IO.File]::WriteAllLines(
        $Path,
        $lines,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Initialize-EnvDefault([string]$Path, [string]$Name, [string]$Value) {
    $lines = [System.Collections.Generic.List[string]]::new()
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $lines.Add($line)
    }
    $pattern = '^\s*' + [regex]::Escape($Name) + '=(.*)$'
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match $pattern) {
            if (-not $Matches[1].Trim()) {
                $lines[$index] = "$Name=$Value"
            }
            [System.IO.File]::WriteAllLines(
                $Path,
                $lines,
                [System.Text.UTF8Encoding]::new($false)
            )
            return
        }
    }
    $lines.Add("$Name=$Value")
    [System.IO.File]::WriteAllLines(
        $Path,
        $lines,
        [System.Text.UTF8Encoding]::new($false)
    )
}

Require-Command git "请先安装 Git。"
Require-Command node "请先安装 Node.js 22.12 或更高版本。"
Require-Command npm "请先安装 npm。"
Require-Command python "请先安装 Python 3.12。"
Require-Command docker "请先安装 Docker Desktop 或 Docker Engine。"

$nodeVersion = [version]((& node --version).TrimStart("v"))
if ($nodeVersion -lt [version]"22.12.0") {
    Write-Warning "Node.js $nodeVersion 低于已验证的 22.12。推荐 Node.js 24 LTS。"
}

Copy-IfMissing (Join-Path $root "model_api_keys.env.example") (Join-Path $parent "model_api_keys.env")
Copy-IfMissing (Join-Path $root ".env.example") (Join-Path $root "infra\.env")
$infraEnv = Join-Path $root "infra\.env"
Initialize-EnvSecret $infraEnv "LIFE_INTERNAL_TOKEN" 32
Initialize-EnvSecret $infraEnv "JWT_SECRET" 32
Initialize-EnvSecret $infraEnv "JWT_REFRESH_SECRET" 32
Initialize-EnvSecret $infraEnv "CREDS_KEY" 32
Initialize-EnvSecret $infraEnv "CREDS_IV" 16
Initialize-EnvSecret $infraEnv "MEILI_MASTER_KEY" 32
Initialize-EnvSecret $infraEnv "MEMOS_BOOTSTRAP_ADMIN_PASSWORD" 32
Initialize-EnvDefault $infraEnv "LIFE_PUBLIC_URL" "http://127.0.0.1:3001"
Initialize-EnvDefault $infraEnv "LIFE_CHAT_INTERNAL_URL" "http://127.0.0.1:3080"
Initialize-EnvDefault $infraEnv "LIFE_ALLOW_REGISTRATION" "true"

if (-not (Test-Path -LiteralPath $upstream)) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $upstream) -Force | Out-Null
    & git clone --branch v0.8.8 --single-branch $LibreChatRepository $upstream
    if ($LASTEXITCODE -ne 0) {
        throw "LibreChat 固定版本克隆失败。"
    }
    & git -C $upstream checkout -b lifecompanion-baseline
    if ($LASTEXITCODE -ne 0) {
        throw "无法创建 LibreChat 本地基线分支。"
    }
}

Copy-IfMissing (Join-Path $upstream ".env.example") (Join-Path $upstream ".env")
$upstreamEnv = Join-Path $upstream ".env"
Initialize-EnvSecret $upstreamEnv "JWT_SECRET" 32
Initialize-EnvSecret $upstreamEnv "JWT_REFRESH_SECRET" 32
Initialize-EnvSecret $upstreamEnv "CREDS_KEY" 32
Initialize-EnvSecret $upstreamEnv "CREDS_IV" 16
Initialize-EnvSecret $upstreamEnv "MEILI_MASTER_KEY" 32

$upstreamHead = (& git -C $upstream rev-parse HEAD).Trim()
$customMarker = Join-Path $upstream "client\src\components\Life\Memories.tsx"
if (-not (Test-Path -LiteralPath $customMarker)) {
    $dirty = (& git -C $upstream status --porcelain)
    if ($dirty) {
        throw "LibreChat 工作树非空但缺少 LifeCompanion 补丁，拒绝覆盖现有修改。"
    }
    if ($upstreamHead -ne $baseCommit) {
        throw "LibreChat HEAD $upstreamHead 与补丁基点 $baseCommit 不一致。"
    }
    & git -C $upstream apply --check $patch
    if ($LASTEXITCODE -ne 0) {
        throw "LibreChat 补丁预检失败。"
    }
    & git -C $upstream apply $patch
    if ($LASTEXITCODE -ne 0) {
        throw "LibreChat 补丁应用失败。"
    }
    Write-Host "[bootstrap] applied $patch"
} else {
    Write-Host "[bootstrap] LifeCompanion upstream patch already present"
}

if (-not $SkipFrontendBuild) {
    Push-Location $upstream
    try {
        & npm ci --ignore-scripts --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) {
            throw "npm ci 失败。"
        }
        & npm run frontend
        if ($LASTEXITCODE -ne 0) {
            throw "LibreChat 前端构建失败。"
        }
    } finally {
        Pop-Location
    }
}

$venv = Join-Path $root "services\life-core\.venv"
$python = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    & python -m venv $venv
    if ($LASTEXITCODE -ne 0) {
        throw "Python 虚拟环境创建失败。"
    }
}
& $python -m pip install --disable-pip-version-check -r (Join-Path $root "services\life-core\requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Python 依赖安装失败。"
}

Write-Host "[bootstrap] complete"
Write-Host "[bootstrap] fill only $(Join-Path $parent 'model_api_keys.env'), then run scripts\start-lifecompanion.ps1"
