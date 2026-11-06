# P02 Stage Log

Current update: 2026-11-04; status remains PARTIAL. The dated 2026-11-03 baseline
below is retained as history. The current configured provider is the existing
DeepSeek endpoint/key with `deepseek-flash`; do not infer the current provider
from historical Zhipu runs.

## 2026-11-04 verified increment

- Real LangMem + DeepSeek + SQLite + Neo4j people/company timeline passed for six
  grounded source facts across twelve days: different companies, current/historical
  employment, invitations, late history, replay, ownership isolation and Core restart.
- Evidence: `evidence/p02/relationships-97b5ef4146644c32.json`.
- The run used 12 requests, 33,756 input tokens and 1,779 output tokens; exact
  attributable cost is UNKNOWN. No new provider/key/account was created.
- Database request budget 12 was verified against the persisted acceptance ledger:
  the next request was stopped before HTTP, with zero additional generation calls.
  See `deepseek-request-budget.json` and `deepseek-usage-summary.json`.
- Real provider UI advertises DeepSeek/`deepseek-flash`; no generation was requested.
  See `deepseek-provider-live-ui.json`.
- Lighthouse remains FAIL: median LCP 6,836.668 ms exceeds the 4,500 ms gate;
  TBT also exceeds its gate. See `deepseek-lighthouse-rerun.txt`.
- The subsequent P03 full backend regression is 88 passed; this does not replace
  missing P02 product acceptance.
- Remaining: LibreChat memory Q&A/source clicks, 100 facts + 100 retrieval benchmark,
  complete source-message deletion propagation, broader alias disambiguation.
  Graphiti remains `BLOCKED_EMBEDDING`.
- A read-only audit on 2026-11-04 at 01:05 local rechecked the actual persisted
  12-call ledger and live five-edge Neo4j projection against the original report.
  No additional model request was made. See `evidence/p03/final-runtime-audit.json`
  and the independent `docs/development-log/2026-11-04_01-05_P02DeepSeek关系时序与配额复核_开发验收.md`.

Date: 2026-11-03 (Asia/Hong_Kong)  
Status: PARTIAL  
Project: `H:\AI For research institute\LifeCompanion-Rebuild`  
Worktree: `.work\p00-p07-20261103`  
Branch: `feat/rebuild-p00-p07-20261103`  
HEAD at stage entry: `e2711c7b87367b39b0e2acdc88f4fb9fde01edf1`

## Scope and safety

- Confirmed the identity guard before each shell operation. All code writes were within the audited Rebuild worktree.
- Used a new ignored P02 virtual environment, P02 Neo4j data directory, and P02-only ports `7475`/`7688`.
- Continued to treat running Silver containers as read-only. No request, restart, or data operation targeted them.
- Used only existing Rebuild Zhipu credentials for synthetic model input. No image generation, new provider account, Git commit, push, migration, or deployment was performed.
- The Neo4j Community server is GPLv3; Python driver is Apache-2.0. Community server distribution/use obligations require separate legal review before redistribution.

## Changes

- Integrated LangMem 0.0.30 with the current configured `glm-4.7` model for structured memory extraction and existing-memory context.
- Added exact-source grounding for evidence, fact values, entity names, and relation endpoints.
- Added SQLite entity/relation records and a retryable graph projection outbox.
- Added Neo4j 5.26.32 projection for memories, entities, evidence, events, and relationships, scoped by Life-core owner ID.
- Added graph keyword and relation-based candidate retrieval; SQLite consent and active state remain authoritative.
- Added fail-closed Graphiti status adapter; native Graphiti remains blocked because no embedding provider is configured.
- Fixed two observed retrieval defects: a missing Neo4j property assignment stopped projection; a U-disk-specific query initially included an unrelated umbrella plan. Both are corrected and covered by real acceptance.
- Future-plan correction now stores only the current plan text while preserving the original source evidence and superseded history.
- Fixed graph withdrawal leaving evidence nodes and entity relationships behind. Cleanup now removes orphan derived content in the owner namespace.
- Added generation-checked outbox acknowledgments, transactional job claims, interrupted-job recovery, and bounded connection timeouts. Verified against real Neo4j with no model calls.
- LangMem existing-memory context now excludes sensitive records after sensitive consent is revoked.

## Runtime verification

- P02 isolated Python `pip check`: PASS.
- Life-core regression suite: 65 passed, 1 upstream LangGraph deprecation warning; exit 0, recorded in `evidence/p02/final-backend-regression.txt`.
- Real model + LangMem + SQLite + Neo4j E2E: PASS for extraction, evidence, cross-conversation U-disk/umbrella, qualifier retention, correction/history, graph source edge, graph keyword retrieval, cross-account recall, new Life-core startup/restore, and graph withdrawal.
- Direct graph smoke: two entity nodes projected; unrelated owner namespace returned zero; withdrawal left zero memory node.
- Neo4j server evidence: authenticated Bolt and Cypher succeeded; version 5.26.32 and three uniqueness constraints recorded.
- Initial failed runs were preserved in ignored P02 runtime diagnostics; the two code defects were fixed and the acceptance reran successfully.

## Evidence

- `../../../../evidence/p02/live-acceptance.json`
- `../../../../evidence/p02/neo4j-service.json`
- `../../../../evidence/p02/venv-freeze.txt`
- `../../../../evidence/p02/graph-recovery.json`
- `../../../../evidence/p02/final-backend-regression.txt`
- `MEMORY_SCHEMA.md`
- `GRAPH_SYNC_RECONCILIATION.md`
- `GRAPHITI_NATIVE_STATUS.md`
- `RETRIEVAL_EVAL.md`
- `MEMORY_E2E.md`

## Remaining acceptance

- Run and report the required 100 fact cases and 100 natural retrieval cases with ranking metrics and latency.
- Validate the complete people/company invitation and employment timeline, entity separation, and historical query scenarios.
- Verify replay, message deletion, and consent withdrawal propagation end to end.
- Exercise the user-facing chat retrieval/source click path in LibreChat after graph-backed recall is live.
- Graphiti native episode and hybrid retrieval remain `BLOCKED_EMBEDDING`.
- Exact model/API cost is UNKNOWN because this integration run did not expose usage metadata.
