"""Owner-scoped semantic forgetting on synthetic data, never real provider/storage."""
import pytest

from app.memory_forget import ForgetSelection, MemoryForget
from test_memory_sources import setup, body, save, vectors


def select(service, monkeypatch, memories=(), sources=(), intent="forget"):
    monkeypatch.setattr(service, "select", lambda *_: ForgetSelection(
        intent=intent, memory_ids=list(memories), source_ids=list(sources)))


def test_forget_scrubs_history_sources_vectors_jobs_and_blocks_replay(setup, monkeypatch):
    memory, alice, bob = setup
    owner = alice['life_user_id']
    source = body(text='我现在住在杭州')
    memory.set_permissions(owner, {'sensitive_consent': True})
    memory.enqueue(alice, source)
    sid = memory.sources.items(owner)[0]['source_id']
    item = save(memory, alice, source, 'fact:residence', '杭州')
    other = body('tea', '我喜欢龙井茶')
    memory.sources.record(alice, other)
    tea = save(memory, alice, other)
    vectors(memory, alice, sid, item['memory_id'], tea['memory_id'])
    service = MemoryForget(memory)
    select(service, monkeypatch, [item['memory_id']], [sid])
    result = service.execute(alice, 'forget-1', 'chat', '忘记住址')
    assert result['status'] == 'forgotten'
    assert [i['memory_id'] for i in memory.list_items(owner)] == [tea['memory_id']]
    assert memory.sources.detail(owner, sid) is None
    with memory.store.connect() as db:
        row = db.execute('select * from memory_items where memory_id=?', (item['memory_id'],)).fetchone()
        assert row['state'] == 'withdrawn' and row['canonical_text'] == row['value'] == ''
        assert db.execute('select text from memory_sources where source_id=?',(sid,)).fetchone()[0] is None
        assert db.execute('select payload from memory_jobs').fetchone()[0] is None
        assert [r[0] for r in db.execute('select memory_id from memory_vectors')] == [tea['memory_id']]
    assert memory.enqueue(alice, {**source, 'source_message_id':'replay'})['status'] == 'revoked'
    monkeypatch.setattr(service, 'select', lambda *_: pytest.fail('receipt must prevent a second model call'))
    assert service.execute(alice, 'forget-1', 'chat', '忘记住址') == result
    assert service.execute(alice, 'forget-1', 'chat', '改为忘记所有资料')['status'] == 'conflict'


def test_item_selection_also_scrubs_siblings_from_the_withdrawn_source(setup, monkeypatch):
    memory, alice, _ = setup
    source = body(text='我住杭州，也喜欢龙井茶')
    memory.sources.record(alice, source)
    residence = save(memory, alice, source, 'fact:residence', '杭州')
    sibling = save(memory, alice, source, 'fact:drink_preference', '龙井茶')
    independent = body('separate', '我喜欢跑步')
    memory.sources.record(alice, independent)
    kept = save(memory, alice, independent, 'fact:interest', '跑步')
    service = MemoryForget(memory)
    select(service, monkeypatch, [residence['memory_id']])
    result = service.execute(alice, 'f', 'c', '忘记住址')
    assert result == {'status': 'forgotten', 'item_count': 2, 'source_count': 1}
    assert [i['memory_id'] for i in memory.list_items(alice['life_user_id'])] == [kept['memory_id']]
    with memory.store.connect() as db:
        assert db.execute('select value from memory_items where memory_id=?',
                          (sibling['memory_id'],)).fetchone()[0] == ''


def test_forget_rejects_foreign_or_fabricated_ids_atomically(setup, monkeypatch):
    memory, alice, bob = setup
    source = body()
    memory.sources.record(alice, source)
    mine = save(memory, alice, source)
    memory.sources.record(bob, source)
    theirs = save(memory, bob, source)
    service = MemoryForget(memory)
    select(service, monkeypatch, [mine['memory_id'], theirs['memory_id']])
    assert service.execute(alice,'f','c','清除偏好')['status'] == 'unavailable'
    assert len(memory.list_items(alice['life_user_id'])) == 1
    assert len(memory.list_items(bob['life_user_id'])) == 1


@pytest.mark.parametrize('intent', ['not_requested', 'clarify'])
def test_no_affirmative_intent_never_deletes_even_with_selected_ids(setup, monkeypatch, intent):
    memory, alice, _ = setup
    memory.sources.record(alice, body())
    item = save(memory, alice, body())
    service = MemoryForget(memory)
    select(service, monkeypatch, [item['memory_id']], intent=intent)
    result = service.execute(alice,'f','c','不要忘记我的喜好')
    assert result['status'] in {'not_requested','needs_input'}
    assert len(memory.list_items(alice['life_user_id'])) == 1


def test_forget_available_with_recall_disabled_and_old_versions_are_scrubbed(setup, monkeypatch):
    memory, alice, _ = setup
    memory.sources.record(alice, body())
    item = save(memory, alice, body())
    memory.invalidate(alice['life_user_id'], item['memory_id'], 'superseded')
    memory.set_permissions(alice['life_user_id'], {'recall_consent':False})
    service = MemoryForget(memory)
    select(service, monkeypatch, [item['memory_id']])
    assert service.execute(alice,'f','c','撤回旧偏好')['status'] == 'forgotten'
    with memory.store.connect() as db:
        assert db.execute('select value from memory_items').fetchone()[0] == ''


def test_changed_target_is_not_deleted(setup, monkeypatch):
    memory, alice, _ = setup
    memory.sources.record(alice, body())
    item = save(memory, alice, body())
    service = MemoryForget(memory)
    def changed(*_):
        with memory.store.connect() as db:
            db.execute('update memory_items set revision=revision+1')
        return ForgetSelection(intent='forget', memory_ids=[item['memory_id']])
    monkeypatch.setattr(service,'select',changed)
    assert service.execute(alice,'f','c','撤回偏好')['code'] == 'FORGET_TARGET_CHANGED'
    assert len(memory.list_items(alice['life_user_id'])) == 1


def test_provider_failure_never_confirms_deletion(setup, monkeypatch):
    memory, alice, _ = setup
    service = MemoryForget(memory)
    def unavailable(*_): raise ValueError('FORGET_UNAVAILABLE')
    monkeypatch.setattr(service,'select',unavailable)
    assert service.execute(alice,'f','c','忘记住址') == {'status':'unavailable'}
