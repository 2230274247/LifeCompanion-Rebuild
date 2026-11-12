"""Publish selected synthetic memories through the official Memos path and verify.

Publication uses life-core's real POST /api/v1/memories/publish (JWT), which calls
Memos' official API and only then marks the event published. The gateway does not
expose this server-side route, so the call targets life-core directly on localhost.
No memo ref or status is faked.
"""
from __future__ import annotations
import json
import time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'infra/runtime/memory-load'
EVIDENCE = ROOT / 'evidence/memory-load-20261109'
GATEWAY = 'http://127.0.0.1:3001'
CORE = 'http://127.0.0.1:8010'


def login(client, account):
    response = client.post(GATEWAY + '/api/auth/login', json={
        'email': account['email'], 'password': account['password'],
    })
    assert response.status_code == 200, 'LOGIN_FAILED'
    return {'Authorization': 'Bearer ' + response.json()['token']}


def main():
    accounts = json.loads((RUNTIME / 'accounts.json').read_text(encoding='utf-8'))
    dataset = json.loads((EVIDENCE / 'dataset.json').read_text(encoding='utf-8'))
    selected = [r for r in dataset['rows'] if r.get('selected_for_publication')]
    results = []
    with httpx.Client(timeout=60, trust_env=False) as client:
        owner = login(client, accounts['owner'])
        outsider = login(client, accounts['outsider'])

        for row in selected:
            started = time.perf_counter()
            response = client.post(CORE + '/api/v1/memories/publish',
                                   headers=owner, json={'event_id': row['event_id']})
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            body = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
            event = body.get('event', {}) if isinstance(body, dict) else {}
            results.append(dict(key=row['key'], event_id=row['event_id'],
                                memory_id=row['memory_id'],
                                http_status=response.status_code,
                                status=event.get('status'), memo_ref=event.get('memo_ref'),
                                elapsed_ms=elapsed,
                                code=(body.get('detail') or {}).get('code') if isinstance(body, dict) else None))
            if (len(results) % 8) == 0:
                print(f'PUBLISH {len(results)}/{len(selected)} published={sum(1 for r in results if r["status"]=="published")}', flush=True)

        published = [r for r in results if r.get('status') == 'published']
        listed = client.get(CORE + '/api/v1/events', headers=owner)
        listed_events = listed.json().get('events', []) if listed.status_code == 200 else []
        by_id = {e['event_id']: e for e in listed_events}
        read_back = []
        for r in published:
            e = by_id.get(r['event_id'], {})
            read_back.append(dict(key=r['key'], event_id=r['event_id'],
                                  published_in_list=e.get('status') == 'published',
                                  memo_ref_matches=e.get('memo_ref') == r['memo_ref']))

        # PRIVATE + creator verified through the read path for one published memory.
        sample = published[0] if published else None
        privacy = None
        if sample:
            owner_read = client.get(CORE + '/api/v1/knowledge/' + sample['memory_id'], headers=owner)
            outsider_read = client.get(CORE + '/api/v1/knowledge/' + sample['memory_id'], headers=outsider)
            privacy = dict(owner_status=owner_read.status_code,
                           owner_content_present=isinstance(owner_read.json(), dict) and bool(owner_read.json().get('content')),
                           outsider_status=outsider_read.status_code)

    summary = dict(
        checked_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        selected=len(selected),
        published=len(published),
        failed=len(results) - len(published),
        read_back_verified=sum(1 for x in read_back if x['published_in_list'] and x['memo_ref_matches']),
        privacy_check=privacy,
        results=results,
        read_back=read_back,
    )
    (EVIDENCE / 'publication-report.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k not in ('results', 'read_back')},
                     ensure_ascii=False, indent=2), flush=True)
    return 0 if summary['published'] == len(selected) else 1


if __name__ == '__main__':
    raise SystemExit(main())
