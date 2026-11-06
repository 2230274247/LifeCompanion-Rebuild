# P02 Memory Schema

Status: PARTIAL, based on Rebuild isolated runtime evidence dated 2026-11-03.

## Sources of truth

- LibreChat Mongo remains the source for original conversations and messages.
- Life-core SQLite remains authoritative for consent, memory records, evidence, revisions, and projection jobs.
- Neo4j Community 5.26.32 is a derived, rebuildable graph projection. It is not the authority for user-visible memory.
- LangMem 0.0.30 proposes structured changes using the configured Zhipu `glm-4.7` model. SQLite validates and persists the result only after source-substring checks.

## Records

| Record | SQLite / source | Purpose |
|---|---|---|
| ChatMessage | LibreChat Mongo | Unmodified original user and assistant messages |
| MemoryItem | `memory_items` | Current and historical facts, occurred events, or future plans |
| MemoryEvidence | `memory_evidence` | Owner, message, conversation, date, content hash, classifier version |
| MemoryRevision | `memory_revisions` | Created, superseded, and withdrawn history |
| Entity | `memory_entities` | Explicitly grounded person, organization, place, or concept |
| Relation | `memory_relations` | Grounded, typed relationship between extracted entities |
| GraphProjectionJob | `memory_graph_jobs` | SQLite outbox state for retryable Neo4j synchronization |
| MemoryEvent | `events` | Existing Rebuild event record linked to memory and source IDs |

Memory records retain `valid_from`, `valid_until`, `revision`, sensitivity, and state. Evidence is keyed by `(memory_id, message_id)`. Recall is scoped by the authenticated Life-core user ID and current consent.

## Graph projection

Nodes: `Memory`, `Entity`, `Evidence`, and `Event`.

Relationships: `HAS_EVIDENCE`, `MENTIONS`, `HAS_EVENT`, `ASSERTS`, and typed `RELATED`. Every node carries an owner namespace or is reachable only from a uniquely namespaced parent. Evidence nodes retain source message and conversation IDs, not copied chat bodies.

Withdrawal clears source evidence and entity data in SQLite, queues graph deletion, and removes the corresponding graph node. Superseded facts remain historical with their validity state.

## Known limits

- Entity and relation extraction is bounded by LangMem's schema and exact source-substring validation; the current live test exercised a stable fact and the direct graph smoke exercised one person-to-organization relation.
- Chinese alias resolution and broad entity disambiguation are not yet evaluated at the P02 target scale.
- SQLite uses the existing schema migration-on-start pattern; a formal versioned migration artifact is still needed.
