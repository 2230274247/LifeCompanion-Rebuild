param(
    [switch]$NoBrowser,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$infra = Join-Path $root "infra"
$runtime = Join-Path $infra "runtime"
$lifeCore = Join-Path $root "services\life-core"
$gateway = Join-Path $root "apps\product-portal"
$librechatRoot = Join-Path $root "products\librechat-custom"
$python = Join-Path $lifeCore ".venv\Scripts\python.exe"
$clientDistIndex = Join-Path $librechatRoot "client\dist\index.html"
$launcherLog = Join-Path $runtime "launcher.log"
$compose = @(
    "--env-file", ".env",
    "-f", "compose.baseline.yaml",
    "-f", "compose.spa.yaml"
)

New-Item -ItemType Directory -Path $runtime -Force | Out-Null

function Write-Log([string]$Message) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
    Add-Content -LiteralPath $launcherLog -Value "$stamp  $Message" -Encoding UTF8
}

function Write-Step([string]$Message) {
    $line = "[拾光] $Message"
    Write-Host $line -ForegroundColor Cyan
    Write-Log $line
}

function Write-Info([string]$Message) {
    Write-Host "       $Message" -ForegroundColor DarkGray
    Write-Log "       $Message"
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
    try {
        return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)
    } catch {
        return $false
    }
}

function Get-PortOwner([int]$Port) {
    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
    } catch {
        return @()
    }
    foreach ($connection in $connections) {
        $ownerPid = $connection.OwningProcess
        $process = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerPid" -ErrorAction SilentlyContinue
        [pscustomobject]@{
            Port = $Port
            PID = $ownerPid
            ProcessName = $process.ProcessName
            ExecutablePath = $process.Path
            CommandLine = $cim.CommandLine
        }
    }
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

function Get-GitInfo {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        return [pscustomobject]@{
            Branch = "unknown (git not found)"
            Commit = "unknown"
            Dirty = $false
        }
    }
    $branch = (& git -C $root rev-parse --abbrev-ref HEAD 2>$null) -join ""
    $commit = (& git -C $root rev-parse HEAD 2>$null) -join ""
    $dirty = ((& git -C $root status --porcelain=v1 2>$null | Measure-Object).Count) -gt 0
    return [pscustomobject]@{
        Branch = $branch
        Commit = $commit
        Dirty = $dirty
    }
}

function Get-NewestSourceTime([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return [DateTime]::MinValue
    }
    $newest = [DateTime]::MinValue
    Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.FullName -match '\\__tests__\\' -or $_.Name -match '\.(spec|test)\.') {
            return
        }
        if ($_.LastWriteTime -gt $newest) {
            $newest = $_.LastWriteTime
        }
    }
    return $newest
}

function Get-FrontendFreshness {
    $distTime = if (Test-Path -LiteralPath $clientDistIndex) {
        (Get-Item -LiteralPath $clientDistIndex).LastWriteTime
    } else {
        [DateTime]::MinValue
    }

    $sourceRoots = @(
        (Join-Path $librechatRoot "client\src"),
        (Join-Path $librechatRoot "packages\data-provider\src"),
        (Join-Path $librechatRoot "packages\api\src"),
        (Join-Path $librechatRoot "packages\client\src"),
        (Join-Path $librechatRoot "packages\data-schemas\src")
    )
    $sourceTime = [DateTime]::MinValue
    foreach ($sourceRoot in $sourceRoots) {
        $candidate = Get-NewestSourceTime $sourceRoot
        if ($candidate -gt $sourceTime) {
            $sourceTime = $candidate
        }
    }

    return [pscustomobject]@{
        DistTime = $distTime
        SourceTime = $sourceTime
        Stale = ($distTime -lt $sourceTime)
    }
}

function Assert-LifeCoreOwner($owner) {
    if ($null -eq $owner) {
        return $false
    }
    $commandMatch =
        $owner.CommandLine -and
        ($owner.CommandLine -match "uvicorn") -and
        ($owner.CommandLine -match "app\.main:app") -and
        ($owner.CommandLine -match "8010")
    return $commandMatch
}

function Assert-GatewayOwner($owner) {
    if ($null -eq $owner) {
        return $false
    }
    return ($owner.ProcessName -eq "node") -and ($owner.CommandLine -match "server\.mjs")
}

function Stop-OwnerProcess($owner, [string]$Label) {
    if ($null -eq $owner) {
        return
    }
    Write-Step "停止已识别的 $Label 进程 PID=$($owner.PID)..."
    Stop-Process -Id $owner.PID -Force -ErrorAction Stop
    Start-Sleep -Seconds 1
}

function Restart-LibreChat {
    Push-Location $infra
    try {
        & docker compose @compose restart librechat
        if ($LASTEXITCODE -ne 0) {
            throw "LibreChat 容器重启失败。"
        }
    } finally {
        Pop-Location
    }
}

# ---- Banner and environment facts ----
Write-Step "拾光桌面一键启动"
Write-Info "项目路径：$root"
$gitInfo = Get-GitInfo
Write-Info "Git 分支：$($gitInfo.Branch)"
Write-Info "Git 提交：$($gitInfo.Commit)"
Write-Info "工作区状态：$(if ($gitInfo.Dirty) { '有未提交改动' } else { '干净' })"
Write-Info "运行模式：$(if ($NoBrowser) { '不自动打开浏览器' } else { '启动后打开浏览器' })；$(if ($SkipBuild) { '跳过前端重建' } else { '必要时重建前端' })"
Write-Info "访问地址：http://127.0.0.1:3001（LibreChat 直连 http://127.0.0.1:3080）"

if (-not (Test-Path -LiteralPath $infra)) {
    throw "项目目录不存在：$root"
}
foreach ($file in @(
    (Join-Path $infra ".env"),
    (Join-Path $librechatRoot ".env"),
    $python
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
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "未找到 docker compose 插件。"
}

Import-EnvFile (Join-Path $infra ".env")
Import-EnvFile (Join-Path $librechatRoot ".env")
$env:PYTHONPATH = $lifeCore
$env:LIFE_DATABASE_PATH = Join-Path $lifeCore "data\life-core.sqlite3"
$env:LIFE_HOST = "127.0.0.1"
$env:LIFE_PORT = "8010"
$env:PORT = "3001"

# ---- Docker ----
Write-Step "检查 Docker..."
& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $dockerCommand = Get-Command docker
    $dockerDesktop = Join-Path (Split-Path (Split-Path (Split-Path $dockerCommand.Source))) "Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        $dockerDesktop = "H:\AI\Docker\App\Docker Desktop.exe"
    }
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        throw "Docker Desktop 未运行，且未找到：$dockerDesktop"
    }
    Write-Step "正在启动 Docker Desktop..."
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

# ---- Frontend freshness and rebuild ----
$freshness = Get-FrontendFreshness
Write-Info "前端 dist 时间：$($freshness.DistTime)"
Write-Info "前端源码最新时间：$($freshness.SourceTime)"
if ($freshness.Stale) {
    if ($SkipBuild) {
        throw "前端源码已过期，但本次指定了 -SkipBuild，未重建。请移除该参数后重试。"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $librechatRoot "node_modules"))) {
        throw "前端源码已过期，但缺少 node_modules，无法安全重建。请先运行 npm install。"
    }
    Write-Step "前端源码已更新，开始重建前端..."
    Push-Location $librechatRoot
    try {
        & npm run frontend
        if ($LASTEXITCODE -ne 0) {
            throw "前端重建失败。"
        }
    } finally {
        Pop-Location
    }
    Write-Step "重启 LibreChat 以加载新前端..."
    Restart-LibreChat
} else {
    Write-Info "前端 dist 为最新，无需重建。"
}

# ---- life-core ----
$lifeCoreHealthy = Test-Health "http://127.0.0.1:8010/health"
if (-not $lifeCoreHealthy) {
    $owners = @(Get-PortOwner 8010)
    if ($owners.Count -gt 0) {
        $owner = $owners[0]
        if (Assert-LifeCoreOwner $owner) {
            Write-Step "端口 8010 上为未就绪的 life-core，准备替换..."
            Stop-OwnerProcess $owner "life-core"
        } else {
            throw "端口 8010 被其他进程占用（PID=$($owner.PID)，$($owner.ExecutablePath)），且无法证明属于当前项目。为避免误杀，启动已停止。"
        }
    }
    Write-Step "启动 life-core..."
    Start-Process -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010") `
        -WorkingDirectory $lifeCore `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runtime "launcher-life-core.out.log") `
        -RedirectStandardError (Join-Path $runtime "launcher-life-core.err.log")
} else {
    $owners = @(Get-PortOwner 8010)
    if ($owners.Count -gt 0 -and -not (Assert-LifeCoreOwner $owners[0])) {
        throw "端口 8010 的进程不属于当前项目，且健康检查通过但无法证明身份。为避免误杀，启动已停止。"
    }
    Write-Step "life-core 已在运行"
}

# ---- Unified gateway ----
$gatewayHealthy = Test-Health "http://127.0.0.1:3001/health"
if (-not $gatewayHealthy) {
    $owners = @(Get-PortOwner 3001)
    if ($owners.Count -gt 0) {
        $owner = $owners[0]
        if (Assert-GatewayOwner $owner) {
            Write-Step "端口 3001 上为未就绪的网关，准备替换..."
            Stop-OwnerProcess $owner "统一入口"
        } else {
            throw "端口 3001 被其他进程占用（PID=$($owner.PID)，$($owner.ExecutablePath)），且无法证明属于当前项目。为避免误杀，启动已停止。"
        }
    }
    Write-Step "启动统一入口..."
    Start-Process -FilePath (Get-Command node).Source `
        -ArgumentList @("server.mjs") `
        -WorkingDirectory $gateway `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runtime "launcher-gateway.out.log") `
        -RedirectStandardError (Join-Path $runtime "launcher-gateway.err.log")
} else {
    $owners = @(Get-PortOwner 3001)
    if ($owners.Count -gt 0 -and -not (Assert-GatewayOwner $owners[0])) {
        throw "端口 3001 的进程不属于当前项目，且健康检查通过但无法证明身份。为避免误杀，启动已停止。"
    }
    Write-Step "统一入口已在运行"
}

Wait-ForHealth "Memos" "http://127.0.0.1:5230/healthz"
Wait-ForHealth "LibreChat" "http://127.0.0.1:3080/health"
Wait-ForHealth "life-core" "http://127.0.0.1:8010/health"
Wait-ForHealth "统一入口" "http://127.0.0.1:3001/health"

if (-not $NoBrowser) {
    Write-Step "打开浏览器..."
    Start-Process "http://127.0.0.1:3001"
}
Write-Step "启动完成：http://127.0.0.1:3001"
