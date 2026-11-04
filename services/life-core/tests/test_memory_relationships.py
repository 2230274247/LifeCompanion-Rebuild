from datetime import datetime

from app.memory import Candidate, MemoryEntity, MemoryRelation
from test_api import bootstrap, make_app
from test_memory_pipeline import auth


def relationship(person, organization, relation_type="works_at"):
    return Candidate(
        candidate_type="stable_fact",
        canonical_text=f"{person}在{organization}工作",
        evidence_quote=f"{person}在{organization}工作",
        occurred_state="occurred",
        experience_owner="self",
        fact_key="relationship",
        value=organization,
        confidence=.9,
        sensitivity="ordinary",
        entities=[
            MemoryEntity(name=person, entity_type="person"),
            MemoryEntity(name=organization, entity_type="organization"),
        ],
        relations=[MemoryRelation(source=person, relation_type=relation_type, target=organization)],
    )


def save(memory, user, person, organization, text, message, at="2026-11-03T10:00:00+08:00",
         relation_type="works_at"):
    now = datetime.fromisoformat(at)
    candidate = relationship(person, organization, relation_type)
    candidate.evidence_quote = text
    key = memory.key_for(candidate, text, now)
    return memory.save(user, candidate, key, message, f"conversation-{message}", text, now)


def test_people_companies_and_invitation_are_distinct(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        uid = bootstrap(client)["life_user_id"]
        memory = app.state.memory
        a = save(memory, uid, "小王", "青禾科技", "小王在青禾科技工作", "a")
        b = save(memory, uid, "小李", "远帆科技", "小李在远帆科技工作", "b")
        c = save(memory, uid, "小陈", "青禾科技", "小陈邀请我加入青禾科技", "c", relation_type="invited")
        assert len({a["semantic_key"], b["semantic_key"], c["semantic_key"]}) == 3
        assert len(memory.list_items(uid)) == 3
        assert "invited" in c["semantic_key"] and "works_at" not in c["semantic_key"]


def test_relationship_timeline_reorders_late_history_without_changing_current(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        uid = bootstrap(client)["life_user_id"]
        memory = app.state.memory
        memory.set_permissions(uid, {"recall_consent": True})
        original = save(memory, uid, "小王", "青禾科技", "2026-10-23小王在青禾科技工作", "a")
        current = save(memory, uid, "小王", "远帆科技",
                       "2026-10-29小王从青禾科技跳槽到远帆科技工作", "b")
        late = save(memory, uid, "小王", "青禾科技", "2026-10-25小王在青禾科技工作", "late")
        assert current["memory_id"] != original["memory_id"]
        assert late["memory_id"] == original["memory_id"]
        assert memory.list_items(uid)[0]["memory_id"] == current["memory_id"]
        historical = memory.detail(uid, original["memory_id"])
        assert historical["state"] == "superseded" and historical["event_end_date"] == "2026-10-29"
        assert historical["event_date"] == "2026-10-23"
        assert len(historical["sources"]) == 2
        now = memory.recall(uid, "小王目前在哪工作")
        then = memory.recall(uid, "2026-10-25小王在哪家公司工作")
        assert len(now) == 1 and now[0]["value"] == "远帆科技"
        assert len(then) == 1 and then[0]["value"] == "青禾科技"


def test_ambiguous_employment_does_not_silently_replace_existing_or_invent_date(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        uid = bootstrap(client)["life_user_id"]
        memory = app.state.memory
        original = save(memory, uid, "小王", "青禾科技", "小王在青禾科技工作", "a")
        uncertain = save(memory, uid, "小王", "远帆科技", "小王在远帆科技工作", "b")
        assert uncertain["conflict"] is True
        assert len(memory.list_items(uid)) == 1
        assert memory.detail(uid, original["memory_id"])["event_date"] is None


def test_relationship_source_replay_and_withdrawal_tombstone(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        uid = bootstrap(client)["life_user_id"]
        memory = app.state.memory
        args = (memory, uid, "小王", "青禾科技", "2026-10-23小王在青禾科技工作", "original")
        item = save(*args)
        again = save(*args)
        assert again["memory_id"] == item["memory_id"]
        assert len(memory.detail(uid, item["memory_id"])["sources"]) == 1
        memory.invalidate(uid, item["memory_id"])
        replayed = save(*args)
        assert replayed["state"] == "withdrawn" and memory.list_items(uid) == []
        bootstrap(client, "lc-user-b", "users/b")
        assert client.get(f"/api/v1/knowledge/{item['memory_id']}", headers=auth("lc-user-b")).status_code == 404
