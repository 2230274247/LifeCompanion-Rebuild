"""Measure live pure-semantic recall; gold targets are never passed to retrieval."""
from __future__ import annotations
import json
import time
import uuid
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'infra/runtime/memory-load'
EVIDENCE = ROOT / 'evidence/memory-load-20261109'
BASE = 'http://127.0.0.1:3001'


def main():
    accounts = json.loads((RUNTIME/'accounts.json').read_text(encoding='utf-8'))
    dataset = json.loads((EVIDENCE/'dataset.json').read_text(encoding='utf-8'))
    by_key = {r['key']:r for r in dataset['rows']}
    by_id = {r['memory_id']:r for r in dataset['rows']}
    checks, results = [], []
    with httpx.Client(timeout=60,trust_env=False) as client:
        for account in accounts.values():
            login = client.post(BASE+'/api/auth/login',json={'email':account['email'],'password':account['password']})
            assert login.status_code == 200, 'SYNTHETIC_LOGIN_FAILED'
            account['token'] = login.json()['token']
        (RUNTIME/'accounts.json').write_text(json.dumps(accounts,ensure_ascii=False,indent=2),encoding='utf-8')
        headers = {'Authorization':'Bearer '+accounts['owner']['token']}
        def recall(query, recent=None, user_headers=headers, conversation=None):
            body = dict(query=query,conversation_id=conversation or str(uuid.uuid4()),source_message_id=str(uuid.uuid4()))
            if recent is not None:
                body['recent_messages'] = [dict(role='user',text=text,conversation_id=body['conversation_id']) for text in recent]
            started = time.perf_counter()
            response = client.post(BASE+'/life-api/api/v1/knowledge/recall',headers=user_headers,json=body)
            if response.status_code != 200:
                raise RuntimeError('RECALL_HTTP_'+str(response.status_code))
            answer = response.json()
            answer['test_conversation_id'] = body['conversation_id']
            return answer, round((time.perf_counter()-started)*1000,2)
        for attempt in range(120):
            readiness,_ = recall('家里的衣物清洁设备出了什么故障？')
            if readiness['retrieval']['semantic_status']=='ready':
                break
            time.sleep(1)
        else:
            raise RuntimeError('SEMANTIC_INDEX_NOT_READY')
        for index, case in enumerate(dataset['questions']):
            answer, elapsed = recall(case['query'])
            ids = [item['memory_id'] for item in answer['items']]
            gold = {by_key[key]['memory_id'] for key in case['expected_keys']}
            rank = min((ids.index(mid)+1 for mid in gold if mid in ids), default=None)
            meta = answer['retrieval']
            results.append(dict(**case,rank=rank,hit_at_1=rank==1,hit_at_3=rank is not None and rank<=3,
                                hit_at_8=rank is not None,elapsed_ms=elapsed,status=answer['status'],retrieval=meta,
                                test_conversation_id=answer['test_conversation_id'],
                                returned=[dict(key=by_id[mid]['key'],text=by_id[mid]['text'],
                                               source_conversation_id=by_id[mid]['conversation_id']) for mid in ids if mid in by_id]))
            checks.append(dict(name='pure_vector_'+case['key'],pass_=meta['mode']=='semantic_only' and meta['keyword_retrieval'] is False))
            checks.append(dict(name='full_index_'+case['key'],pass_=meta.get('indexed_count')==400))
            if case['kind']=='dated_paraphrase':
                checks.append(dict(name='date_filter_'+case['key'],pass_=all(by_id[mid]['bucket']==case['bucket'] for mid in ids)))
            checks.append(dict(name='cross_conversation_'+case['key'],pass_=all(
                mid in by_id and by_id[mid]['conversation_id'] != answer['test_conversation_id'] for mid in ids)))
            if (index+1)%24==0:
                print(f'QUERIES {index+1}/{len(dataset["questions"])} hit_at_8={sum(r["hit_at_8"] for r in results)}',flush=True)
        contextual = []
        for bucket,index,anchor in [('1d',2,'家中清洗衣物的设备出了故障'),
                                    ('3d',34,'查订单的网络服务变得很慢'),
                                    ('7d',70,'我学的新证据改变概率判断的方法'),
                                    ('1m',71,'我学弹六根弦的乐器时碰到了困难')]:
            target = by_key[f'{bucket}-{index:03d}']
            query = target['occurred_at'][:10]+'，那件事我后来怎么处理的？'
            answer, elapsed = recall(query,recent=[anchor])
            ids = [i['memory_id'] for i in answer['items']]
            rank = ids.index(target['memory_id'])+1 if target['memory_id'] in ids else None
            contextual.append(dict(bucket=bucket,anchor=anchor,query=query,expected_key=target['key'],rank=rank,
                                   elapsed_ms=elapsed,metadata=answer['retrieval']))
        relative_tests = []
        for phrase,bucket in [('1天前','1d'),('3天前','3d'),('1周前','7d'),('1个月前','1m')]:
            target = by_key[bucket+'-002']
            answer,elapsed = recall(phrase+'家里的衣物清洁设备出了什么故障，又如何解决？')
            ids = [i['memory_id'] for i in answer['items']]
            relative_tests.append(dict(query=phrase,expected_key=target['key'],
                hit=target['memory_id'] in ids,returned_keys=[by_id[mid]['key'] for mid in ids],
                date_isolated=all(by_id[mid]['bucket']==bucket for mid in ids),
                retrieval=answer['retrieval'],elapsed_ms=elapsed))
        negative_questions = [
            '我参加世界杯决赛时进了几个球？', '我在北极冰层下考察时拍到了什么？',
            '我驾驶载人飞船登陆火星后做了哪些实验？', '我接受心脏移植手术的医院叫什么？',
            '我负责建造的核潜艇采用什么推进方式？', '我第一次跳伞在哪里降落？',
            '我竞选市长时提出了什么交通政策？', '我养的鳄鱼叫什么名字？',
            '我训练的赛马在什么比赛获胜？', '我设计的大型粒子加速器有什么成果？']
        negatives = []
        for question in negative_questions:
            answer,elapsed = recall(question)
            negatives.append(dict(query=question,false_positive=bool(answer['items']),
                                  returned=answer['items'],retrieval=answer['retrieval'],elapsed_ms=elapsed))
        outsider_headers = {'Authorization':'Bearer '+accounts['outsider']['token']}
        answer,_ = recall('我自制甜点时出现了什么技术失误？',user_headers=outsider_headers)
        checks.append(dict(name='outsider_no_private_results',pass_=answer['items']==[] and answer['profile']==[]))
        victim = by_key['1m-002']['memory_id']
        denied = client.get(BASE+'/life-api/api/v1/knowledge/'+victim,headers=outsider_headers)
        checks.append(dict(name='outsider_detail_404',pass_=denied.status_code==404))
        off = client.patch(BASE+'/life-api/api/v1/me/settings',headers=headers,json={'recall_consent':False})
        assert off.status_code == 200
        denied,_ = recall('我处理过哪些家庭设备故障？')
        checks.append(dict(name='revoked_recall_denied',pass_=denied['status']=='permission_denied' and not denied['items']))
        on = client.patch(BASE+'/life-api/api/v1/me/settings',headers=headers,json={'recall_consent':True})
        assert on.status_code == 200
        # Re-index after permission revocation purged this user's vectors.
        for attempt in range(60):
            ready,_ = recall('我处理过哪些家庭设备故障？')
            if ready['retrieval']['semantic_status']=='ready':
                break
            time.sleep(1)
        checks.append(dict(name='regrant_rebuilds_index',pass_=ready['retrieval'].get('indexed_count')==400))
    counts = Counter(r['bucket'] for r in results if r.get('bucket'))
    latencies = sorted(r['elapsed_ms'] for r in results)
    summary = dict(checked_at=datetime.now(UTC).isoformat(),dataset_count=400,questions=len(results),
                   hit_at_1=sum(r['hit_at_1'] for r in results),hit_at_3=sum(r['hit_at_3'] for r in results),
                   hit_at_8=sum(r['hit_at_8'] for r in results),p50_ms=latencies[len(latencies)//2],
                   p95_ms=latencies[int(len(latencies)*0.95)],
                   per_bucket={b:dict(questions=n,hit_at_8=sum(r['hit_at_8'] for r in results if r.get('bucket')==b)) for b,n in counts.items()},
                   context_tests=contextual,context_hits=sum(c['rank'] is not None for c in contextual),
                   relative_time_tests=relative_tests,relative_time_hits=sum(r['hit'] for r in relative_tests),
                   negative_tests=negatives,negative_count=len(negatives),
                   negative_false_positives=sum(n['false_positive'] for n in negatives),
                   safety_checks=len(checks),safety_failures=[c['name'] for c in checks if not c['pass_']],
                   published=dataset['published'],selected=dataset['selected'],results=results)
    (EVIDENCE/'recall-report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('results','context_tests','negative_tests')},ensure_ascii=False,indent=2),flush=True)
    return 0 if not summary['safety_failures'] else 1

if __name__=='__main__':
    raise SystemExit(main())
