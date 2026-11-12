"""Calendar truth is independent of recording time, provider arithmetic and indexing."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.occurrence import Occurrence, explicit_occurrence, initialize_occurrence
from app.retrieval import MemoryRetriever, _item_day
from test_api import bootstrap, make_app
from test_memory_pipeline import auth

ANCHOR = datetime(2026, 11, 2, 10, tzinfo=ZoneInfo('Asia/Shanghai'))


@pytest.mark.parametrize('text, expected', [
    ('上周六我去了香山', ('2026-10-31', '2026-10-31', 'day')),
    ('上周日我参观了展览', ('2026-11-01', '2026-11-01', 'day')),
    ('上上周三我参加了活动', ('2026-10-21', '2026-10-21', 'day')),
    ('上个月我搬家了', ('2026-10-01', '2026-10-31', 'month')),
    ('上上个月我参加了聚会', ('2026-09-01', '2026-09-30', 'month')),
    ('去年我参加了比赛', ('2025-01-01', '2025-12-31', 'year')),
    ('上周我完成了报告', ('2026-10-26', '2026-11-01', 'week')),
    ('昨天我完成了报告', ('2026-11-01', '2026-11-01', 'day')),
    ('2024年2月29日我参加了活动', ('2024-02-29', '2024-02-29', 'day')),
    ('2024年2月我旅行了', ('2024-02-01', '2024-02-29', 'month')),
    ('我参加了陶艺展览', (None, None, 'unknown')),
    ('很久以前我参加了活动', (None, None, 'unknown')),
    ('今天和昨天我都散步了', (None, None, 'unknown')),
    ('2026年2月30日我参加了活动', (None, None, 'unknown')),
    ('2027年1月1日我参加了活动', (None, None, 'unknown')),
])
def test_calendar_precision_and_no_recording_date_default(text, expected):
    assert explicit_occurrence(text).bounds(ANCHOR) == expected


def test_symbolic_normalization_generalizes_beyond_literal_calendar_patterns():
    spec = Occurrence(expression='距离这条消息三个月之前', unit='month', offset=-3)
    assert spec.bounds(ANCHOR) == ('2026-08-01', '2026-08-31', 'month')
    assert Occurrence(expression='上周六', unit='week', offset=-1, weekday=5).bounds(ANCHOR)[0] == '2026-10-31'
    with pytest.raises(ValueError):
        Occurrence(expression='上个月', unit='month', offset=-1, day=9)


def test_month_rollover_and_user_timezone():
    january = datetime(2026, 1, 1, tzinfo=ZoneInfo('Asia/Shanghai'))
    assert explicit_occurrence('上个月旅行了').bounds(january) == ('2025-12-01', '2025-12-31', 'month')
    message = datetime.fromisoformat('2026-11-01T16:30:00+00:00').astimezone(ZoneInfo('Asia/Shanghai'))
    assert explicit_occurrence('昨天散步了').bounds(message)[0] == '2026-11-01'


def test_legacy_upgrade_preserves_values_without_blessing_message_dates(tmp_path):
    import sqlite3
    path = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        db.execute('create table memory_items (memory_id text, semantic_key text, canonical_text text)')
        db.execute("insert into memory_items values ('legacy','event:2026-11-02:old','上个月搬家')")
        db.commit()
        with sqlite3.connect(tmp_path / 'before-upgrade.sqlite') as backup:
            db.backup(backup)
        initialize_occurrence(db, 'memory_items')
        initialize_occurrence(db, 'memory_items')
        row = dict(db.execute('select * from memory_items').fetchone())
        assert row['canonical_text'] == '上个月搬家'
        assert row['occurrence_precision'] == 'unknown' and row['occurrence_start'] is None
        assert _item_day({**row, 'kind':'life_event', 'valid_from':ANCHOR.isoformat()}, ANCHOR.tzinfo) is None


def test_ingest_and_overview_use_intervals_and_leave_unknown_out(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        user = bootstrap(client)
        client.patch('/api/v1/me/settings', headers=auth(), json={'recall_consent':True})
        monkeypatch.setattr(app.state.memos, 'create_private_memo', lambda event: 'memos/'+event['event_id'])
        monkeypatch.setattr(app.state.memos, 'get_private_memo', lambda *_: {'content':'合成事件','tags':[]})
        for mid, text in [('month','上个月我搬家去了新社区。'), ('saturday','上周六我去了香山散步。'),
                          ('unknown','我参加了陶艺展览。')]:
            result = client.post('/internal/v1/events/ingest',headers={'X-Internal-Token':'test-internal'},json={
                'source_user_id':'lc-user-a','source_message_id':mid,'conversation_id':mid,
                'text':text,'occurred_at':ANCHOR.isoformat()})
            assert result.status_code == 200 and result.json()['accepted'], result.text
        items = app.state.memory.list_items(user['life_user_id'])
        month = next(i for i in items if '上个月' in i['canonical_text'])
        unknown = next(i for i in items if '陶艺' in i['canonical_text'])
        assert month['occurrence_precision']=='month' and month['occurrence_start']=='2026-10-01'
        assert month['valid_from']==ANCHOR.isoformat()
        assert _item_day(month, ANCHOR.tzinfo) is None
        assert unknown['occurrence_precision']=='unknown'
        retriever = app.state.memory.retriever
        october = retriever.overview(user['life_user_id'], window=(date(2026,10,1),date(2026,10,31)))
        november = retriever.overview(user['life_user_id'], window=(date(2026,11,1),date(2026,11,30)))
        assert len(october['items'])==2 and november['items']==[]
        assert october['retrieval']['total_count']==2
        listing = client.get('/api/v1/memories',headers=auth())
        assert listing.status_code==200 and listing.json()['total']==3
        assert len(client.get('/api/v1/memories?on_date=2026-10-31',headers=auth()).json()['memories'])==2
        assert client.get('/api/v1/memories?on_date=2026-11-02',headers=auth()).json()['total']==0
        # Withdrawal clears newly introduced temporal metadata too.
        app.state.memory.invalidate(user['life_user_id'], month['memory_id'])
        assert app.state.memory.detail(user['life_user_id'],month['memory_id'])['occurrence_start'] is None
