"""Drive real chat as the synthetic owner, without reading provider credentials."""
import json
import time
import uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'infra/runtime/memory-load'
EVIDENCE=ROOT/'evidence/memory-load-20261109'
BASE='http://127.0.0.1:3001'


def main():
    accounts=json.loads((RUNTIME/'accounts.json').read_text(encoding='utf-8'))
    dataset=json.loads((EVIDENCE/'dataset.json').read_text(encoding='utf-8'))
    rows={r['key']:r for r in dataset['rows']}
    cases=[('1d-002','家里的衣物清洁设备出了什么故障，又如何解决？'),
           ('1m-071','我练乐器时遇到什么手指控制问题？')]
    results=[]
    with httpx.Client(timeout=180,trust_env=False) as client:
        owner=accounts['owner']
        logged=client.post(BASE+'/api/auth/login',json={'email':owner['email'],'password':owner['password']})
        assert logged.status_code==200
        token=logged.json()['token']
        headers={'Authorization':'Bearer '+token,'X-LibreChat-Generation-Protocol':'2',
                 'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}
        models=client.get(BASE+'/api/models',headers=headers)
        assert models.status_code==200
        public=models.json()
        print('MODEL_NAMES',json.dumps(public.get('DeepSeek',[]),ensure_ascii=False),flush=True)
        for key,question in cases:
            target=rows[key]
            query=target['occurred_at'][:10]+'那天，'+question
            body=dict(text=query,sender='User',isCreatedByUser=True,messageId=str(uuid.uuid4()),
                parentMessageId='00000000-0000-0000-0000-000000000000',conversationId='new',
                endpoint='DeepSeek',endpointType='custom',model='deepseek-chat',
                clientRequestId='memory-load-'+str(uuid.uuid4()),generationProtocolVersion=2)
            started=time.perf_counter()
            response=client.post(BASE+'/api/agents/chat/DeepSeek',headers=headers,json=body)
            print('CHAT_STARTED',key,response.status_code,flush=True)
            if response.status_code not in (200,201,202):
                results.append(dict(key=key,status='start_failed',http_status=response.status_code))
                continue
            events=[]
            conversation=None
            def consume(lines):
                for line in lines:
                    if not line.startswith('data: '):
                        continue
                    try:
                        item=json.loads(line[6:])
                    except ValueError:
                        continue
                    events.append(item)
                    if item.get('final') is not None:
                        break
            print('CHAT_CONTENT_TYPE',response.headers.get('content-type'), 'BYTES',len(response.content),flush=True)
            if not response.content:
                results.append(dict(key=key,status='empty_chat_response',http_status=response.status_code))
                continue
            if response.text.lstrip().startswith('<'):
                results.append(dict(key=key,status='html_instead_of_chat',http_status=response.status_code))
                continue
            if 'text/event-stream' in response.headers.get('content-type','') or response.text.startswith('event:') or response.text.startswith('data:'):
                consume(response.iter_lines())
                for event in reversed(events):
                    for field in ('requestMessage','responseMessage','message','conversation'):
                        record=event.get(field,{})
                        conversation=conversation or (record.get('conversationId') if isinstance(record,dict) else None)
            else:
                info=response.json()
                conversation=info.get('conversationId',info.get('streamId'))
                params={'generationProtocolVersion':2}
                if info.get('generationCreatedAt') is not None:
                    params['generationCreatedAt']=info['generationCreatedAt']
                elif info.get('createdAt') is not None:
                    params['generationCreatedAt']=info['createdAt']
                with client.stream('GET',BASE+'/api/agents/chat/stream/'+info['streamId'],headers=headers,params=params) as stream:
                    if stream.status_code!=200:
                        results.append(dict(key=key,status='stream_failed',http_status=stream.status_code))
                        continue
                    consume(stream.iter_lines())
            # These events contain synthetic account text only; raw envelopes stay private.
            (RUNTIME/(key+'-chat-events.json')).write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
            final=next((e for e in reversed(events) if e.get('final') is not None),{})
            message=final.get('responseMessage',{})
            content=message.get('text','')
            if not content:
                content='\n'.join(p.get('text','') for p in message.get('content',[]) if p.get('type')=='text')
            trace=client.get(BASE+'/life-api/api/v1/memory-status',headers=headers,params={'conversation_id':conversation})
            trace_body=trace.json() if trace.status_code==200 else {}
            result=dict(key=key,query=query,conversation_id=conversation,
                original_conversation_id=target['conversation_id'],different_conversation=bool(conversation) and conversation!=target['conversation_id'],
                expected_memory_id=target['memory_id'],elapsed_ms=round((time.perf_counter()-started)*1000,2),
                completed=bool(final),response=content,source_link_in_reply=('/knowledge/'+target['memory_id']) in content,
                trace=trace_body,event_count=len(events),event_shapes=[sorted(e.keys()) for e in events[-3:]])
            results.append(result)
            print('CHAT_RESULT',key,'completed='+str(result['completed']),'source_link='+str(result['source_link_in_reply']),flush=True)
    passed=all(r.get('completed') and r.get('different_conversation') and r.get('source_link_in_reply') for r in results)
    (EVIDENCE/'real-chat-report.json').write_text(json.dumps(dict(passed=passed,results=results),ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if passed else 1

if __name__=='__main__':
    raise SystemExit(main())
