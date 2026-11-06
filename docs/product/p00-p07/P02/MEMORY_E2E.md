# P02 Memory End-to-End

Result: PARTIAL overall. Real backend APIs, configured model, SQLite, and Neo4j were exercised on 2026-11-03; the LibreChat browser chat and source-click path remain unverified.

| Case | Result | Evidence |
|---|---|---|
| Real LangMem extraction to SQLite | PASS | `evidence/p02/live-acceptance.json` |
| Source evidence persisted | PASS, one evidence row | Same |
| U-disk + umbrella across conversations through Life-core API | PASS | Same |
| Preserve negative color qualifier | PASS | Same |
| Correct future plan and retain history | PASS | Same |
| Neo4j source edge and keyword retrieval | PASS | Same |
| Cross-account recall | PASS for tested synthetic accounts | Same |
| Fresh Life-core startup and SQLite recall | PASS | Same |
| Withdrawal propagation to Neo4j | PASS | Same |
| Full person/company 12-day timeline | PASS for six grounded synthetic facts, late history, replay and restart | `evidence/p02/relationships-97b5ef4146644c32.json` (2026-11-04 local date) |
| Message deletion and replay after withdrawal | NOT RUN | — |
| 100 + 100 benchmark suite | NOT RUN | — |
| Native Graphiti episode flow | BLOCKED_EMBEDDING | `GRAPHITI_NATIVE_STATUS.md` |

All live provider inputs were synthetic. Image consent was false. No image provider was called.
The 2026-11-04 DeepSeek increment captured complete usage (12 requests, 33,756 input,
1,779 output tokens); exact attributable cost remains UNKNOWN. The older baseline
did not expose usage. Browser memory Q&A and source clicks are still unverified.
