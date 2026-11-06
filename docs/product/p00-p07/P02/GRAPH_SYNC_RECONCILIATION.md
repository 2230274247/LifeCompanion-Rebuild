# P02 Graph Sync and Reconciliation

Status: PARTIAL. Real isolated SQLite-to-Neo4j writes, source edges, keyword search, and deletion were exercised on 2026-11-03.

## Write path

1. `MemoryService.save` writes the memory, evidence, entities, relations, and a `memory_graph_jobs` row to SQLite.
2. The life-core worker claims queued rows and projects current SQLite state to Neo4j.
3. Successful projection marks the outbox job `succeeded`.
4. Failures retain a generic error code and retry with bounded exponential delay; the job becomes `failed` after eight attempts.
5. A replay writes the same graph IDs and relationships, making the projection idempotent.

The outbox uses a monotonic `generation` counter. Claiming uses a SQLite immediate transaction; an acknowledgment can complete only the generation it claimed. A newer write or withdrawal therefore remains queued even if an older projection finishes afterward. Interrupted `running` jobs are reset to `queued` on isolated single-worker startup.

## Revoke path

1. `MemoryService.invalidate` changes the source record state and queues a graph job.
2. Withdrawn records clear evidence and entity/relation content in SQLite.
3. The graph worker deletes the corresponding `Memory` node, its derived entity-to-entity relationships, and orphan entity/evidence/event nodes in that owner's namespace.
4. Superseded records remain with historical state and validity metadata.

## Rebuild and audit

SQLite is authoritative, so a future reconciliation command can requeue graph jobs by comparing each user's active SQLite records with graph IDs. The current worker supports idempotent projection and retry, but a complete scheduled drift scanner and operator repair endpoint remain unimplemented.

## Rebuild evidence

- `../../../../evidence/p02/neo4j-service.json`: authenticated Bolt connectivity, Neo4j version, and constraints.
- `../../../../evidence/p02/live-acceptance.json`: real LangMem ingestion, graph evidence edge, keyword retrieval, restart restore, and withdrawal.
- `../../../../evidence/p02/graph-recovery.json`: real relation/evidence cleanup, unrelated owner preservation, stale acknowledgment protection, interrupted job recovery, and real Neo4j authentication-failure recovery. No model calls.
- The acceptance used synthetic accounts and the P02-only graph service on `127.0.0.1:7688`.
