from __future__ import annotations

from datetime import UTC, datetime, timedelta

from neo4j import GraphDatabase

from .store import Store, utc_now


class GraphProjector:
    def __init__(self, store: Store, settings):
        self.store = store
        self.driver = (
            GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
                connection_timeout=3,
                connection_acquisition_timeout=5,
                max_transaction_retry_time=0,
            )
            if settings.neo4j_uri and settings.neo4j_password
            else None
        )

    def initialize(self):
        if self.driver is None:
            return
        self.driver.verify_connectivity()
        with self.driver.session() as session:
            session.run(
                "CREATE CONSTRAINT lc_memory_id IF NOT EXISTS "
                "FOR (m:Memory) REQUIRE m.memory_id IS UNIQUE"
            ).consume()
            session.run(
                "CREATE CONSTRAINT lc_entity_key IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE (e.owner_id, e.entity_key) IS UNIQUE"
            ).consume()
            session.run(
                "CREATE CONSTRAINT lc_evidence_key IF NOT EXISTS "
                "FOR (e:Evidence) REQUIRE (e.owner_id, e.message_id) IS UNIQUE"
            ).consume()

    def run_one(self):
        if self.driver is None:
            return False
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM memory_graph_jobs WHERE status='queued' AND updated_at<=? "
                "ORDER BY updated_at LIMIT 1",
                (utc_now(),),
            ).fetchone()
            if row is None:
                return False
            db.execute(
                "UPDATE memory_graph_jobs SET status='running',attempts=attempts+1,updated_at=? "
                "WHERE memory_id=?",
                (utc_now(), row["memory_id"]),
            )
        try:
            self.project(row["user_id"], row["memory_id"])
        except Exception:
            with self.store.connect() as db:
                attempts = row["attempts"] + 1
                next_status = "failed" if attempts >= 8 else "queued"
                retry_at = (datetime.now(UTC) + timedelta(seconds=min(3600, 2 ** attempts))).isoformat()
                db.execute(
                    "UPDATE memory_graph_jobs SET status=?,last_error='GRAPH_PROJECTION_FAILED',"
                    "updated_at=? WHERE memory_id=? AND generation=? AND status='running'",
                    (next_status, retry_at, row["memory_id"], row["generation"]),
                )
        else:
            with self.store.connect() as db:
                db.execute(
                    "UPDATE memory_graph_jobs SET status='succeeded',last_error=NULL,updated_at=? "
                    "WHERE memory_id=? AND generation=? AND status='running'",
                    (utc_now(), row["memory_id"], row["generation"]),
                )
        return True

    def search_memory_ids(self, user_id: str, query: str, as_of: str | None = None) -> set[str]:
        if self.driver is None:
            return set()
        terms = sorted({query[i:i + 2] for i in range(max(0, len(query) - 1))})
        relation_type = None
        if any(word in query for word in ("邀请", "介绍")):
            relation_type = "invited"
        elif any(word in query for word in ("工作", "任职", "公司", "同事")):
            relation_type = "works_at"
        elif any(word in query for word in ("加入", "入职")):
            relation_type = "joined"
        try:
            with self.driver.session() as session:
                rows = session.run(
                    "MATCH (m:Memory {owner_id:$owner_id}) "
                    "WHERE (($as_of IS NULL AND m.state='active') OR "
                    "($as_of IS NOT NULL AND m.state IN ['active','superseded'] "
                    "AND m.event_date <= $as_of AND (m.event_end_date IS NULL OR m.event_end_date > $as_of))) AND ("
                    "EXISTS { MATCH (m)-[a:ASSERTS]->() "
                    "WHERE $relation_type IS NOT NULL AND a.type=$relation_type } "
                    "OR EXISTS { MATCH (m)-[:MENTIONS]->(e:Entity) "
                    "WHERE any(term IN $terms WHERE toLower(e.name) CONTAINS term "
                    "OR term CONTAINS toLower(e.name)) } "
                    "OR any(term IN $terms WHERE toLower(m.text) CONTAINS term "
                    "OR term CONTAINS toLower(m.text))) "
                    "RETURN DISTINCT m.memory_id AS memory_id",
                    owner_id=user_id,
                    terms=terms,
                    relation_type=relation_type,
                    as_of=as_of,
                )
                return {row["memory_id"] for row in rows}
        except Exception:
            return set()

    def project(self, user_id: str, memory_id: str):
        with self.store.connect() as db:
            db.execute("BEGIN")
            memory = db.execute(
                "SELECT * FROM memory_items WHERE user_id=? AND memory_id=?",
                (user_id, memory_id),
            ).fetchone()
            evidence = db.execute(
                "SELECT message_id,conversation_id,evidence_date FROM memory_evidence "
                "WHERE user_id=? AND memory_id=?",
                (user_id, memory_id),
            ).fetchall()
            entities = db.execute(
                "SELECT entity_key,name,entity_type FROM memory_entities "
                "WHERE user_id=? AND memory_id=?",
                (user_id, memory_id),
            ).fetchall()
            relations = db.execute(
                "SELECT source_key,relation_type,target_key FROM memory_relations "
                "WHERE user_id=? AND memory_id=?",
                (user_id, memory_id),
            ).fetchall()
            event = (
                db.execute(
                    "SELECT event_id,occurred_at,title,status FROM events "
                    "WHERE user_id=? AND event_id=?",
                    (user_id, memory["event_id"]),
                ).fetchone()
                if memory and memory["event_id"]
                else None
            )

        owner_id = user_id
        if memory is None or memory["state"] == "withdrawn" or not evidence:
            with self.driver.session() as session:
                session.execute_write(self._delete_memory, owner_id, memory_id)
            return

        with self.driver.session() as session:
            session.execute_write(
                self._write_memory,
                owner_id,
                dict(memory),
                [dict(row) for row in evidence],
                [dict(row) for row in entities],
                [dict(row) for row in relations],
                dict(event) if event else None,
            )

    @staticmethod
    def _delete_memory(tx, owner_id, memory_id):
        tx.run(
            "MATCH (s:Entity {owner_id:$owner_id})-[r:RELATED {memory_id:$memory_id}]->() "
            "DELETE r",
            owner_id=owner_id,
            memory_id=memory_id,
        ).consume()
        tx.run(
            "MATCH (m:Memory {owner_id:$owner_id,memory_id:$memory_id}) DETACH DELETE m",
            owner_id=owner_id,
            memory_id=memory_id,
        ).consume()
        tx.run(
            "MATCH (e {owner_id:$owner_id}) "
            "WHERE (e:Entity OR e:Evidence OR e:Event) AND NOT (e)--() DELETE e",
            owner_id=owner_id,
        ).consume()

    @staticmethod
    def _write_memory(tx, owner_id, memory, evidence, entities, relations, event):
        tx.run(
            "MERGE (m:Memory {owner_id:$owner_id,memory_id:$memory_id}) "
            "SET m.kind=$kind,m.semantic_key=$semantic_key,m.text=$text,m.state=$state,"
            "m.valid_from=$valid_from,m.valid_until=$valid_until,m.revision=$revision,"
            "m.event_date=$event_date,m.event_end_date=$event_end_date,"
            "m.updated_at=$updated_at",
            owner_id=owner_id,
            memory_id=memory["memory_id"],
            kind=memory["kind"],
            semantic_key=memory["semantic_key"],
            text=memory["canonical_text"],
            state=memory["state"],
            valid_from=memory["valid_from"],
            valid_until=memory["valid_until"],
            revision=memory["revision"],
            event_date=memory["event_date"],
            event_end_date=memory["event_end_date"],
            updated_at=memory["updated_at"],
        ).consume()
        tx.run(
            "MATCH (m:Memory {owner_id:$owner_id,memory_id:$memory_id}) "
            "OPTIONAL MATCH (m)-[r:HAS_EVIDENCE|MENTIONS|HAS_EVENT|ASSERTS]->() DELETE r",
            owner_id=owner_id,
            memory_id=memory["memory_id"],
        ).consume()
        tx.run(
            "MATCH (s:Entity {owner_id:$owner_id})-[r:RELATED {memory_id:$memory_id}]->() DELETE r",
            owner_id=owner_id,
            memory_id=memory["memory_id"],
        ).consume()
        for item in evidence:
            tx.run(
                "MERGE (e:Evidence {owner_id:$owner_id,message_id:$message_id}) "
                "SET e.conversation_id=$conversation_id,e.evidence_date=$evidence_date "
                "WITH e MATCH (m:Memory {owner_id:$owner_id,memory_id:$memory_id}) "
                "MERGE (m)-[:HAS_EVIDENCE]->(e)",
                owner_id=owner_id,
                memory_id=memory["memory_id"],
                message_id=item["message_id"],
                conversation_id=item["conversation_id"],
                evidence_date=item["evidence_date"],
            ).consume()
        entity_keys = {item["entity_key"] for item in entities}
        for entity in entities:
            tx.run(
                "MERGE (e:Entity {owner_id:$owner_id,entity_key:$entity_key}) "
                "SET e.name=$name,e.entity_type=$entity_type "
                "WITH e MATCH (m:Memory {owner_id:$owner_id,memory_id:$memory_id}) "
                "MERGE (m)-[:MENTIONS]->(e)",
                owner_id=owner_id,
                memory_id=memory["memory_id"],
                entity_key=entity["entity_key"],
                name=entity["name"],
                entity_type=entity["entity_type"],
            ).consume()
        for relation in relations:
            if relation["source_key"] not in entity_keys or relation["target_key"] not in entity_keys:
                continue
            tx.run(
                "MATCH (m:Memory {owner_id:$owner_id,memory_id:$memory_id}) "
                "MATCH (s:Entity {owner_id:$owner_id,entity_key:$source_key}) "
                "MATCH (t:Entity {owner_id:$owner_id,entity_key:$target_key}) "
                "MERGE (m)-[:ASSERTS {type:$relation_type}]->(t) "
                "MERGE (s)-[r:RELATED {type:$relation_type,memory_id:$memory_id}]->(t) "
                "SET r.state=$state,r.event_date=$event_date,r.event_end_date=$event_end_date,"
                "r.learned_at=$learned_at",
                owner_id=owner_id,
                memory_id=memory["memory_id"],
                source_key=relation["source_key"],
                target_key=relation["target_key"],
                relation_type=relation["relation_type"],
                state=memory["state"],
                event_date=memory["event_date"],
                event_end_date=memory["event_end_date"],
                learned_at=memory["created_at"],
            ).consume()
        if event:
            tx.run(
                "MERGE (e:Event {owner_id:$owner_id,event_id:$event_id}) "
                "SET e.occurred_at=$occurred_at,e.title=$title,e.status=$status "
                "WITH e MATCH (m:Memory {owner_id:$owner_id,memory_id:$memory_id}) "
                "MERGE (m)-[:HAS_EVENT]->(e)",
                owner_id=owner_id,
                memory_id=memory["memory_id"],
                event_id=event["event_id"],
                occurred_at=event["occurred_at"],
                title=event["title"],
                status=event["status"],
            ).consume()

    def close(self):
        if self.driver:
            self.driver.close()
