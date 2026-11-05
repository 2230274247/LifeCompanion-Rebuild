# V0.2.2 Evidence Index

## Reminder Dialog (evidence/v022-reminder-dialog/)

| File | Description |
|------|-------------|
| p0-1-baseline-audit.json | P0-1 baseline audit result |
| p0-2-current-account-ready.json | P0-2 account provisioning |
| p0-2-live-provisioning.json | P0-2 live provisioning |
| p0-2-real-token-renewal.json | P0-2 token renewal |
| p0-3-live-drafts.json | P0-3 draft lifecycle |
| p0-4-preview-0930.png | P0-4 09:30 preview screenshot |
| p0-4-preview-1015.png | P0-4 10:15 preview screenshot |
| p0-4-before-confirm.json | P0-4 pre-confirm state |
| p0-4-confirmed-refresh.png | P0-4 confirmed + refresh screenshot |
| p0-5-live-delivery.json | P0-5 delivery chain |
| p0-5-in-app-accepted.jpg | P0-5 ntfy in-app accepted |
| p0-5-live-boundaries.json | P0-5 revocation/boundary checks |
| original-sqlite-preservation.json | Original data preservation audit |
| backend-final-49.txt | Backend pytest 49 pass |
| client-original-122-final.txt | Client Jest 122 pass |
| client-new-4-final.txt | Client reminder card 4 pass |
| client-reference-fix-test.txt | Reference scroll fix Jest output |
| build-client-reference-fix.txt | Client production build log |
| acceptance-matrix.md | This matrix |
| failure-log.md | Known failures and gaps |
| command-manifest.md | Reproduction commands |
| chat-{390,430,768,1440,1920}-stable.jpg | Viewport stability screenshots |
| reminders-*-stable.jpg | Reminders page viewport screenshots |
| permissions-*-stable.jpg | Permissions page viewport screenshots |

## Zhipu (evidence/v022-zhipu/)

| File | Description |
|------|-------------|
| provider-preflight.json | Zhipu provider preflight |
| live-integration-*.json | Real integration tests |
| legacy-chat-success.png | Legacy DeepSeek alias through Zhipu |
| configure-*.json | Configuration runs |
| backend-tests.txt | Backend test output |

## Runtime (infra/runtime/v022-reminder-dialog/)

| File | Description |
|------|-------------|
| life-core-before-v022.sqlite3 | Pre-V0.2.2 SQLite backup |
| life-core.sqlite3 | Current SQLite |
| accounts.json | Synthetic test accounts |
| delivery-state.json | Delivery test state |
| session-{a,b,c,d}.dpapi | DPAPI-encrypted session tokens |
| lighthouse-{final,isolated}.log | Lighthouse attempts |
