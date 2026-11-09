"""Pure-vector contract: intentionally replaces keyword/fallback expectations."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.retrieval import MemoryRetriever, _day
from test_hybrid_retrieval import memory, put, NOW


class Vectors:
    model_name = 'controlled-semantic-test-v1'
    status = 'ready'

    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.query_calls = []

    def embed(self, texts):
        self.calls.extend(texts)
        return [self.rows.get(t, [0, 1, 0]) for t in texts]

    def query_embed(self, texts):
        self.query_calls.extend(texts)
        return [[1, 0, 0] for _ in texts]


def search(memory, rows=None):
    return MemoryRetriever(memory, Vectors(rows or {}), now=lambda zone: NOW.astimezone(zone))


def test_semantics_wins_over_identical_text(memory):
    put(memory, 'meaning', '饭后绕着河岸走了一圈')
    put(memory, 'literal', '今天做了哪些活动')
    r = search(memory, {'饭后绕着河岸走了一圈': [1,0,0], '今天做了哪些活动':[0,1,0]})
    r.prepare_user('alice')
    got = r.retrieve('alice', '今天做了哪些活动')
    assert [i['memory_id'] for i in got['items']] == ['meaning']
    assert got['retrieval']['keyword_retrieval'] is False
    assert got['retrieval']['mode'] == 'semantic_only'


def test_same_content_encodes_once_but_preserves_both_memory_sources(memory):
    put(memory, 'a', '午后在河岸散步')
    put(memory, 'b', '午后在河岸散步')
    r = search(memory, {'午后在河岸散步': [1,0,0]})
    assert r.prepare_user('alice') == 2
    assert r.embedder.calls == ['午后在河岸散步']
    assert {i['memory_id'] for i in r.retrieve('alice', '我曾做过什么活动')['items']} == {'a', 'b'}


def test_configured_large_model_missing_cache_never_loads_or_downloads(memory, monkeypatch):
    import sys
    from app.embedding import LARGE_MODEL_NAME
    memory.settings.memory_embedding_model = LARGE_MODEL_NAME
    memory.settings.memory_embedding_cache.mkdir()
    def unexpected(**kwargs):
        pytest.fail('missing pinned cache must not construct/download model')
    monkeypatch.setitem(sys.modules, 'fastembed', SimpleNamespace(TextEmbedding=unexpected))
    r = MemoryRetriever(memory)
    assert r.embedder.model_name == LARGE_MODEL_NAME
    assert r.warmup() == 'cache_missing'


def test_explicit_date_is_metadata_not_encoded_content(memory):
    put(memory, 'a', '下水管恢复畅通')
    r = search(memory, {'下水管恢复畅通': [1,0,0]})
    r.prepare_user('alice')
    got = r.retrieve('alice', '2026-11-08那天，家里的洗衣设备故障怎么解决的')
    assert [i['memory_id'] for i in got['items']] == ['a']
    assert r.embedder.query_calls == ['家里的洗衣设备故障怎么解决的']


def test_no_lexical_fallback_when_model_missing(memory):
    put(memory, 'literal', '公园散步')
    r = search(memory)
    r.embedder.status = 'cache_missing'
    got = r.retrieve('alice', '公园散步')
    assert got['status'] == 'unavailable' and got['items'] == []


def test_all_400_candidates_including_oldest_are_searched(memory):
    with memory.store.connect() as db:
        for index in range(400):
            text = '不相关记录' + str(index) if index != 399 else '远古正确答案'
            stamp = (NOW-timedelta(days=index)).isoformat()
            db.execute('''INSERT INTO memory_items(memory_id,user_id,kind,semantic_key,canonical_text,
                value,state,importance,confidence,sensitivity,image_candidate,valid_from,created_at,updated_at)
                VALUES (?,?, 'life_event',?,?,'','active',0.5,1,'ordinary',0,?,?,?)''',
                (str(index),'alice',f'event:2026-01-01:{index}',text,stamp,stamp,stamp))
    r = search(memory, {'远古正确答案':[1,0,0]})
    assert r.prepare_user('alice') == 400
    got = r.retrieve('alice', '我曾经做过的那段经历')
    assert got['items'][0]['memory_id'] == '399'
    assert got['retrieval']['semantic_candidates'] == 400
    assert got['retrieval']['indexed_count'] == 400


def test_permission_and_user_isolation_and_physical_vector_purge(memory):
    put(memory, 'a', '只有甲知道的经历')
    put(memory, 'b', '只有乙知道的经历', user='bob')
    r = search(memory, {'只有甲知道的经历':[1,0,0], '只有乙知道的经历':[1,0,0]})
    r.prepare_user('alice'); r.prepare_user('bob')
    assert [i['memory_id'] for i in r.retrieve('alice','我做过什么')['items']] == ['a']
    memory.set_permissions('alice', {'recall_consent':False})
    assert r.retrieve('alice','我做过什么')['status'] == 'permission_denied'
    with memory.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM memory_vectors WHERE user_id='alice'").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM memory_vectors WHERE user_id='bob'").fetchone()[0] == 1


def test_withdrawn_memory_never_returns_cached_vector(memory):
    put(memory, 'a', '曾经有的记录')
    r = search(memory, {'曾经有的记录':[1,0,0]})
    r.prepare_user('alice')
    memory.invalidate('alice','a')
    assert r.retrieve('alice','我以前做过什么')['items'] == []
    with memory.store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM memory_vectors').fetchone()[0] == 0


def test_sensitive_filter_precedes_encoding(memory):
    put(memory,'safe','日常散步')
    put(memory,'private','医疗诊断',sensitivity='sensitive')
    r = search(memory, {'日常散步':[1,0,0], '医疗诊断':[1,0,0]})
    r.prepare_user('alice')
    assert '医疗诊断' not in r.embedder.calls
    assert [i['memory_id'] for i in r.retrieve('alice','有什么活动')['items']] == ['safe']


def test_context_can_bridge_anaphora_without_entity_text_filter(memory):
    put(memory, 'a', '下水管恢复畅通')
    put(memory, 'b', '演示投影失败后改用屏幕共享')
    full = '家中洗衣设备的故障\n那件事情怎么解决的'
    r = search(memory, {'下水管恢复畅通':[1,0,0], full:[1,0,0]})
    r.prepare_user('alice')
    got = r.retrieve('alice','那件事情怎么解决的', recent_messages=[{'role':'user','text':'家中洗衣设备的故障'}])
    assert [i['memory_id'] for i in got['items']] == ['a']
    assert got['retrieval']['context_source'] == 'recent_users'


@pytest.mark.parametrize('query,expected', [('1天前',date(2026,11,8)),('三天前',date(2026,11,6)),
    ('一周前',date(2026,11,2)),('一个月前',date(2026,10,9))])
def test_relative_date_metadata_constraints(query,expected):
    assert _day(query,date(2026,11,9)) == expected


def test_calendar_month_end_uses_valid_previous_month_day():
    assert _day('一个月前',date(2026,3,31)) == date(2026,2,28)


def test_public_recall_cannot_supply_owner_or_bypass_auth(tmp_path):
    from test_api import make_app, bootstrap
    from test_memory_pipeline import auth
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        assert client.post('/api/v1/knowledge/recall',json={'query':'经历'}).status_code == 401
        assert client.post('/api/v1/knowledge/recall',headers=auth(),json={
            'query':'经历','source_user_id':'other'}).status_code == 422
        response = client.post('/api/v1/knowledge/recall',headers=auth(),json={'query':'经历'})
        assert response.status_code == 200 and response.json()['status'] == 'permission_denied'
