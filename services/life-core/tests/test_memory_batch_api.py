from datetime import datetime
from zoneinfo import ZoneInfo
from test_api import make_app, bootstrap
from test_memory_pipeline import auth


def send(client, text, source='multi-source', conversation='chat-a'):
    return client.post('/internal/v1/events/ingest', headers={'X-Internal-Token':'test-internal'}, json={
        'source_user_id':'lc-user-a', 'source_message_id':source, 'conversation_id':conversation,
        'text':text, 'occurred_at':datetime.now(ZoneInfo('Asia/Hong_Kong')).isoformat()})


def test_one_message_retains_multiple_facts_with_original_source_and_replay(tmp_path):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        client.patch('/api/v1/me/settings', headers=auth(), json={'sensitive_consent': True, 'recall_consent': True})
        response = send(client, '我的生日是六月十五日。我最喜欢喝无糖拿铁。我是一名软件工程师。')
        assert response.status_code == 200 and response.json()['accepted']
        rows = client.get('/api/v1/knowledge', headers=auth()).json()['items']
        assert len(rows) == 3
        for row in rows:
            detail = app.state.memory.detail(row['user_id'], row['memory_id'])
            assert detail['sources'][0]['message_id'] == 'multi-source'
        assert send(client, '我的生日是六月十五日。我最喜欢喝无糖拿铁。我是一名软件工程师。').status_code == 200
        assert len(app.state.memory.list_items(rows[0]['user_id'])) == 3
        recalled = client.get('/api/v1/knowledge/recall?q=我的生日', headers=auth()).json()['items']
        assert any('六月十五日' in i['canonical_text'] for i in recalled)


def test_distinct_events_in_one_message_have_distinct_publications(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        monkeypatch.setattr(app.state.memos, 'create_private_memo', lambda event:'memos/'+event['event_id'])
        result = send(client, '今天加入了甲项目组。今天加入了乙项目组。')
        assert result.status_code == 200
        user = app.state.store.get_user_by_librechat_id('lc-user-a')
        events = app.state.store.list_events(user['life_user_id'])
        assert len(events) == 2 and events[0]['memo_ref'] != events[1]['memo_ref']
        assert all(e['source_message_ids'] == ['multi-source'] for e in events)
        send(client, '今天加入了甲项目组。今天加入了乙项目组。')
        assert len(app.state.store.list_events(user['life_user_id'])) == 2


def test_negative_preference_never_becomes_positive(tmp_path):
    _, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        assert send(client, '我现在不喜欢咖啡。').status_code == 200
        rows = client.get('/api/v1/knowledge', headers=auth()).json()['items']
        assert rows and all(r['canonical_text'] != '喜欢喝咖啡' for r in rows)


def test_current_avoidance_supersedes_previously_positive_profile(tmp_path):
    _, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        client.patch('/api/v1/me/settings', headers=auth(), json={'recall_consent': True})
        send(client, '我喜欢咖啡', source='positive')
        send(client, '我现在不喜欢咖啡', source='negative')
        rows = client.get('/api/v1/knowledge', headers=auth()).json()['items']
        assert len(rows) == 1 and rows[0]['canonical_text'] == '不喜欢喝咖啡'
        recalled = client.get('/api/v1/knowledge/recall?q=咖啡', headers=auth()).json()['items']
        assert recalled and all('不喜欢' in i['canonical_text'] for i in recalled)


def test_multiple_interests_and_completed_batch_replay(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        assert send(client, '我的爱好是游泳和摄影').json()['accepted']
        rows = client.get('/api/v1/knowledge', headers=auth()).json()['items']
        assert len(rows) == 2 and {r['value'] for r in rows} == {'游泳', '摄影'}
        def forbidden(*args, **kwargs):
            raise AssertionError('completed batches must not call the provider again')
        monkeypatch.setattr(app.state.memory, 'classify_many', forbidden)
        assert send(client, '我的爱好是游泳和摄影').json()['accepted']


def test_batch_retries_failed_publication_without_duplicate_events(tmp_path, monkeypatch):
    import httpx
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        calls = []
        def publish(event):
            calls.append(event['event_id'])
            if len(calls) == 2:
                raise httpx.ConnectError('synthetic failure')
            return 'memos/'+event['event_id']
        monkeypatch.setattr(app.state.memos, 'create_private_memo', publish)
        text = '今天加入了甲项目组。今天加入了乙项目组。'
        assert send(client, text).status_code == 502
        assert send(client, text).json()['accepted']
        owner = app.state.store.get_user_by_librechat_id('lc-user-a')['life_user_id']
        events = app.state.store.list_events(owner)
        assert len(events) == 2 and all(e['status'] == 'published' for e in events)
        assert len(calls) == 3
        statuses = {t['status'] for t in app.state.memory.trace.recent(owner)['traces'] if t['stage'] == 'publication'}
        assert statuses == {'failed', 'published'}
