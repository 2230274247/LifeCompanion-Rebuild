# V0.2.2 Acceptance Matrix

| ID | Item | Status | Evidence |
|----|------|--------|----------|
| P0-1 | Baseline read-only audit | **PASS** | vidence/v022-reminder-dialog/p0-1-baseline-audit.json |
| P0-2 | Current account ready & live provisioning | **PASS** | p0-2-current-account-ready.json, p0-2-live-provisioning.json, p0-2-real-token-renewal.json |
| P0-3 | Draft lifecycle | **PASS** | p0-3-live-drafts.json |
| P0-4 | Preview → confirm → refresh persistence | **PASS** | p0-4-preview-0930.png, p0-4-preview-1015.png, p0-4-confirmed-refresh.png, browser reference-scroll re-verified |
| P0-5 | Real due-time delivery | **PASS** (device push UNKNOWN) | p0-5-live-delivery.json, p0-5-in-app-accepted.jpg |
| P0-5 | Revocation & cross-account boundaries | **PASS** | p0-5-live-boundaries.json |
| ZH | Zhipu API replacement (provider, streaming, title, memory, reminder extraction) | **PASS** | vidence/v022-zhipu/provider-preflight.json, live-integration-*.json, legacy-chat-success.png |
| ZH-KEY | Local admin key entry | **PASS** | infra/runtime/zhipu-api.local.txt, scripts/configure-zhipu.py |
| ZH-WEB | Web admin config UI / hide switch | **NOT IMPLEMENTED** | — |
| REF | Ambiguous reference scroll-to-source | **PASS** (fix applied) | client-reference-fix-test.txt, browser re-verification |
| DATA | Original data preservation | **PARTIAL** | original-sqlite-preservation.json — 0 deletions, 2 rows changed (1 unexplained) |
| PERF | Lighthouse / performance | **BLOCKED** | lighthouse-final.log, lighthouse-isolated.log |
| BE | Backend pytest (49) | **PASS** (historical) | ackend-final-49.txt |
| FE | Client Jest (122 + 4 new) | **PASS** | client-original-122-final.txt, client-new-4-final.txt, client-reference-fix-test.txt |
| BUILD | Client production build | **PASS** | uild-client-reference-fix.txt |
| TC | TypeScript typecheck (3 packages) | **PASS** (historical) | 	ypecheck-*-final.txt |
| LINT | ESLint / sort-imports / Prettier | **PASS** (historical) | slint-final.txt, sort-imports-final.log, prettier-final.log |
| GW | Gateway tests (2) | **PASS** (historical) | gateway-tests.txt |

## Overall Verdict

**V0.2.2: PARTIAL**

Core reminder dialog chain (P0-1 through P0-5) and Zhipu replacement are verified with real browser, real LLM, real Vikunja webhook, and real ntfy delivery. Remaining gaps: unexplained permission-row change, no Lighthouse score, web admin UI not implemented.
