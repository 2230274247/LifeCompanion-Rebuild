# V0.2.2 Architecture & Product Updates

## Zhipu Local Configuration

- Provider: `LIFE_LLM_PROVIDER=zhipu`
- Endpoint: `https://open.bigmodel.cn/api/paas/v4/`
- Model: `glm-4.7` (verified)
- Key source: `infra/runtime/zhipu-api.local.txt` (git-ignored runtime file)
- Configuration script: `scripts/configure-zhipu.py` — validates provider before writing, creates DPAPI-encrypted rollback backup
- Missing key behavior: fails closed; no fallback to DeepSeek
- Thinking mode: disabled for Zhipu (not supported)
- Legacy alias: `life-companion` endpoint in librechat.yaml still labeled DeepSeek but actually routes through Zhipu-compatible spec, so old conversations remain functional

## Local Administrator Entry

- NOT a web admin UI
- NOT a hide switch
- Plain text file under git-ignored runtime directory
- User fills API key manually, then configuration script validates and applies
- Future: web-based admin panel with visibility toggle (not implemented)

## Device Delivery

- Status: **UNKNOWN**
- ntfy accepts push and in-app inbox reads it
- Cannot confirm mobile OS notification delivery
- Do not claim device push PASS

## Lighthouse

- Default port 3080: conflicted with running service
- Isolated port 3098: E2E setup expected English "Sign up" text; product UI is Chinese
- No valid Lighthouse score available
- Do not claim performance PASS

## Original Data Anomaly

- 0 original rows deleted across all tables
- 1 `users` row: only `updated_at` changed (expected provisioning bookkeeping)
- 1 `memory_permissions` row: `recall_consent`, `sensitive_consent`, `updated_at` changed without attributed logged operation
- Resolution: preserve as-is; do not restore; report PARTIAL
