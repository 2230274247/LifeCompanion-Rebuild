param(
    [int]$GatewayPort = 3001,
    [int]$CorePort = 8010,
    [int]$ChatPort = 3080,
    [int]$MemosPort = 5230
)

$checks = @(
    @{ name = "gateway"; url = "http://127.0.0.1:$GatewayPort/health" },
    @{ name = "life-core"; url = "http://127.0.0.1:$CorePort/health" },
    @{ name = "librechat"; url = "http://127.0.0.1:$ChatPort/health" },
    @{ name = "memos"; url = "http://127.0.0.1:$MemosPort/healthz" }
)

$failed = $false
$results = foreach ($check in $checks) {
    try {
        $response = Invoke-WebRequest -Uri $check.url -UseBasicParsing -TimeoutSec 8
        if ($response.StatusCode -ne 200) {
            $failed = $true
        }
        [ordered]@{
            service = $check.name
            status = if ($response.StatusCode -eq 200) { "PASS" } else { "FAIL" }
            http_status = $response.StatusCode
            url = $check.url
        }
    } catch {
        $failed = $true
        [ordered]@{
            service = $check.name
            status = "FAIL"
            http_status = $null
            url = $check.url
            error = $_.Exception.Message
        }
    }
}

$results | ConvertTo-Json -Depth 4
if ($failed) {
    exit 1
}
