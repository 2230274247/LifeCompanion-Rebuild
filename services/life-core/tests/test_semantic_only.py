"""Pure-vector contract: intentionally replaces keyword/fallback expectations."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.retrieval import MemoryRetriever, _day, _range, _rewrite_query
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


def test_same_content_encodes_once_but_result_deduplicates_identical_text(memory):
    put(memory, 'a', '午后在河岸散步')
    put(memory, 'b', '午后在河岸散步')
    r = search(memory, {'午后在河岸散步': [1,0,0]})
    assert r.prepare_user('alice') == 2
    assert r.embedder.calls == ['午后在河岸散步']
    got = r.retrieve('alice', '我曾做过什么活动')
    assert len(got['items']) == 1 and got['items'][0]['memory_id'] in {'a', 'b'}
    assert got['retrieval']['dedup_dropped'] == 1


def test_duplicate_content_across_dates_collapses_to_one_slot(memory):
    # 用户真实失败：同一事实按 4 个时段重复，曾淹没 top-8、挤掉其他不同事实。
    for i, day in enumerate([8, 5, 2, 1]):
        put(memory, f'calligraphy-{i}', '老师提醒我写字要横平竖直',
            semantic_key=f"event:2026-11-{day:02d}:calligraphy")
    put(memory, 'math', '老师提醒我做题要检查')
    r = search(memory, {'老师提醒我写字要横平竖直': [1,0,0], '老师提醒我做题要检查': [1,0,0]})
    r.prepare_user('alice')
    got = r.retrieve('alice', '老师提醒我注意什么')
    hit_ids = [i['memory_id'] for i in got['items']]
    assert 'math' in hit_ids
    assert sum(1 for i in hit_ids if i.startswith('calligraphy')) == 1
    assert got['retrieval']['dedup_dropped'] == 3


def test_rerank_reorders_bi_encoder_candidates_when_ready(memory):
    # 双塔余弦同分无法区分时，交叉编码器应给出真实相关顺序。
    put(memory, 'a', '老师提醒我写字要横平竖直')
    put(memory, 'b', '老师提醒我做题要检查')
    r = search(memory, {'老师提醒我写字要横平竖直': [1,0,0], '老师提醒我做题要检查': [1,0,0]})
    r.prepare_user('alice')
    r.reranker.status = 'ready'

    def fake_rerank(query, docs):
        assert docs == ['老师提醒我写字要横平竖直', '老师提醒我做题要检查']
        return [3.0, 6.0]  # b 更相关

    r.reranker.rerank = fake_rerank
    got = r.retrieve('alice', '老师提醒我注意什么')
    assert got['retrieval']['rerank_used'] is True
    assert got['retrieval']['rerank_pool'] == 2
    assert [i['memory_id'] for i in got['items']] == ['b', 'a']


def test_rerank_not_ready_falls_back_to_bi_encoder_ordering(memory):
    put(memory, 'a', '老师提醒我写字要横平竖直')
    r = search(memory, {'老师提醒我写字要横平竖直': [1,0,0]})
    r.prepare_user('alice')
    got = r.retrieve('alice', '老师提醒我注意什么')
    assert got['retrieval']['rerank_used'] is False
    assert [i['memory_id'] for i in got['items']] == ['a']


def test_rewrite_query_returns_original_without_llm_key():
    assert _rewrite_query(SimpleNamespace(), '总结老师提醒我注意什么', {}) == '总结老师提醒我注意什么'


def test_query_rewrite_replaces_embedded_query_when_enabled(memory, monkeypatch):
    put(memory, 'a', '老师提醒我写字要横平竖直')
    r = search(memory, {'老师提醒我写字要横平竖直': [1,0,0]})
    r.prepare_user('alice')
    monkeypatch.setattr('app.retrieval._rewrite_query', lambda settings, q, cache: '写字横平竖直 做题检查')
    got = r.retrieve('alice', '老师提醒我注意什么')
    assert got['retrieval']['query_rewritten'] is True
    assert r.embedder.query_calls == ['写字横平竖直 做题检查']
    assert [i['memory_id'] for i in got['items']] == ['a']


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


@pytest.mark.parametrize('query,expected', [
    ('近15天', (date(2026,10,26), date(2026,11,9))),
    ('近一个月', (date(2026,10,9), date(2026,11,9))),
    ('近3个月', (date(2026,8,9), date(2026,11,9))),
    ('本月', (date(2026,11,1), date(2026,11,9))),
    ('上个月', (date(2026,10,1), date(2026,10,31))),
    ('上周', (date(2026,11,2), date(2026,11,8))),
    ('这周', (date(2026,11,9), date(2026,11,9))),
    ('最近几天', (date(2026,11,6), date(2026,11,9))),
    ('最近', (date(2026,10,27), date(2026,11,9))),
])
def test_range_metadata_constraints(query, expected):
    assert _range(query, date(2026,11,9)) == expected


def test_non_temporal_query_has_no_range_constraint():
    assert _range('总结老师提醒我注意什么', date(2026,11,9)) is None
    assert _range('11月5日的日程', date(2026,11,9)) is None


def test_range_constrains_candidates_to_window(memory):
    put(memory, 'old', '旧时段的日程记录', semantic_key="event:2026-10-01:old",
        valid_from=NOW - timedelta(days=40))
    put(memory, 'recent', '最近时段的日程记录', semantic_key="event:2026-11-07:recent",
        valid_from=NOW - timedelta(days=2))
    r = search(memory, {'旧时段的日程记录': [1,0,0], '最近时段的日程记录': [1,0,0]})
    r.prepare_user('alice')
    got = r.retrieve('alice', '近15天的日程')
    assert [i['memory_id'] for i in got['items']] == ['recent']
    assert got['retrieval']['semantic_candidates'] == 1
    assert got['retrieval']['indexed_count'] == 2


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
