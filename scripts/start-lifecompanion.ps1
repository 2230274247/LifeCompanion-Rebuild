param(
    [switch]$NoBrowser,
    [string]$Python = $env:LIFE_PYTHON,
    [int]$CorePort = 8010,
    [int]$GatewayPort = 3001,
    [int]$ChatPort = 3080,
    [int]$MemosPort = 5230
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$infra = Join-Path $root "infra"
$runtime = Join-Path $infra "runtime"
$lifeCore = Join-Path $root "services\life-core"
$gateway = Join-Path $root "apps\product-portal"
if (-not $Python) {
    $Python = Join-Path $lifeCore ".venv\Scripts\python.exe"
}
$compose = @(
    "--env-file", ".env",
    "-f", "compose.baseline.yaml",
    "-f", "compose.spa.yaml"
)

function Write-Step([string]$Message) {
    Write-Host "[拾光] $Message" -ForegroundColor Cyan
}

function Test-Health([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-Port([int]$Port) {
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Import-EnvFile([string]$Path) {
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match '^\s*#' -or $line -notmatch '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            continue
        }
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
    }
}

function Wait-ForHealth([string]$Name, [string]$Url, [int]$Seconds = 90) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Health $Url) {
            Write-Step "$Name 已就绪"
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "$Name 在 $Seconds 秒内未通过健康检查：$Url"
}

if (-not (Test-Path -LiteralPath $infra)) {
    throw "项目目录不存在：$root"
}
foreach ($file in @(
    (Join-Path $infra ".env"),
    (Join-Path $root "products\librechat-custom\.env"),
    $Python
)) {
    if (-not (Test-Path -LiteralPath $file)) {
        throw "缺少启动文件：$file"
    }
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "未找到 Node.js，请确认 node 已加入 PATH。"
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "未找到 Docker，请确认 docker 已加入 PATH。"
}

New-Item -ItemType Directory -Path $runtime -Force | Out-Null
Import-EnvFile (Join-Path $infra ".env")
Import-EnvFile (Join-Path $root "products\librechat-custom\.env")
$env:PYTHONPATH = $lifeCore
$env:LIFE_DATABASE_PATH = Join-Path $lifeCore "data\life-core.sqlite3"
$env:LIFE_HOST = "127.0.0.1"
$env:LIFE_PORT = "$CorePort"
$env:PORT = "$GatewayPort"
$env:LIFE_LIBRECHAT_PORT = "$ChatPort"
$env:LIFE_MEMOS_PORT = "$MemosPort"
$env:LIFE_CORE_HOST_URL = "http://host.docker.internal:$CorePort"
$env:MEMOS_BASE_URL = "http://127.0.0.1:$MemosPort"
$env:LIFE_ALLOWED_ORIGINS = "http://localhost:$GatewayPort,http://127.0.0.1:$GatewayPort"
$env:CHAT_TARGET = "http://127.0.0.1:$ChatPort"
$env:LIFE_TARGET = "http://127.0.0.1:$CorePort"

Write-Step "检查 Docker..."
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $dockerCommand = Get-Command docker
    $dockerDesktop = Join-Path (Split-Path (Split-Path (Split-Path $dockerCommand.Source))) "Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    }
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        $dockerDesktop = Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe"
    }
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        throw "Docker Desktop 未运行，且在标准安装路径中未找到 Docker Desktop。请手动启动 Docker 后重试。"
    }
    Write-Step "正在启动 Docker Desktop，首次启动可能需要 1-2 分钟..."
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(120)
    do {
        Start-Sleep -Seconds 3
        & docker info *> $null
    } until ($LASTEXITCODE -eq 0 -or (Get-Date) -ge $deadline)
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop 在 120 秒内未就绪。"
    }
}
Write-Step "Docker 已就绪"

Write-Step "启动 LibreChat、Memos 及其基础容器..."
Push-Location $infra
try {
    & docker compose @compose up -d
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose 启动失败。"
    }
} finally {
    Pop-Location
}

if (Test-Path -LiteralPath (Join-Path $infra ".env.reminders")) {
    Write-Step "启动已配置的 Vikunja 与 ntfy 本地服务..."
    Push-Location $infra
    try {
        & docker compose --env-file .env.reminders -f compose.reminders.yaml up -d
        if ($LASTEXITCODE -ne 0) {
            throw "提醒服务启动失败。"
        }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Health "http://127.0.0.1:$CorePort/health")) {
    if (Test-Port $CorePort) {
        throw "端口 $CorePort 已被其他进程占用，但 life-core 健康检查失败。为避免误杀进程，启动已停止。"
    }
    Write-Step "启动 life-core..."
    Start-Process -FilePath $Python `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$CorePort") `
        -WorkingDirectory $lifeCore `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runtime "launcher-life-core.out.log") `
        -RedirectStandardError (Join-Path $runtime "launcher-life-core.err.log")
} else {
    Write-Step "life-core 已在运行"
}

if (-not (Test-Health "http://127.0.0.1:$GatewayPort/health")) {
    if (Test-Port $GatewayPort) {
        throw "端口 $GatewayPort 已被其他进程占用，但统一入口健康检查失败。为避免误杀进程，启动已停止。"
    }
    Write-Step "启动统一入口..."
    Start-Process -FilePath (Get-Command node).Source `
        -ArgumentList @("server.mjs") `
        -WorkingDirectory $gateway `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runtime "launcher-gateway.out.log") `
        -RedirectStandardError (Join-Path $runtime "launcher-gateway.err.log")
} else {
    Write-Step "统一入口已在运行"
}

Wait-ForHealth "Memos" "http://127.0.0.1:$MemosPort/healthz"
Wait-ForHealth "LibreChat" "http://127.0.0.1:$ChatPort/health"
Wait-ForHealth "life-core" "http://127.0.0.1:$CorePort/health"
Wait-ForHealth "统一入口" "http://127.0.0.1:$GatewayPort/health"

if (-not $NoBrowser) {
    Write-Step "打开浏览器..."
    Start-Process "http://127.0.0.1:$GatewayPort"
}
Write-Step "启动完成：http://127.0.0.1:$GatewayPort"
