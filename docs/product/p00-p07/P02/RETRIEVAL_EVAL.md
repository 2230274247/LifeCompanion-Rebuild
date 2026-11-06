# P02 Retrieval Evaluation

Status: PARTIAL; the broad evaluation set has not been run.

## Real checks completed

- One real `glm-4.7` LangMem extraction produced a grounded stable preference; SQLite retained one evidence row.
- Cross-conversation U-disk and umbrella plans were recalled together, preserving the green/not-silver qualifier.
- An explicit plan correction created one current blue U-disk result and retained the old version as superseded.
- Querying by U-disk no longer returns the umbrella plan after topic filtering.
- A graph keyword query returned the owning memory ID; another synthetic user namespace returned no result.
- Reopening the same isolated SQLite database restored recall after a fresh Life-core startup.

Evidence: `../../../../evidence/p02/live-acceptance.json`.

## Not measured

- The required 100 fact merge/conflict/negation/entity/time cases.
- The required 100 natural-language retrieval cases and Precision@k, Recall@k, MRR, latency P50/P95, false merge, and missed merge rates.
- Independent human review of ambiguous Chinese aliases.
- Exact attributable provider cost remains UNKNOWN. The initial integration did not
  expose usage; the 2026-11-04 DeepSeek relationship run did: 12 requests, 33,756
  input and 1,779 output tokens. Account balance delta was 0.00 CNY but is not
  reliable per-run attribution.

## 2026-11-04 targeted extension

Six actual grounded facts were extracted through DeepSeek/LangMem and queried
through real local HTTP/SQLite/Neo4j. Current and past employment, distinct
companies, invitations, late history, replay, isolation and restart passed.
This is a targeted extension, not the required 100+100 broad evaluation.
See `evidence/p02/relationships-97b5ef4146644c32.json`.
