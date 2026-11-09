"""Read synthetic historical sources through the normal authenticated chat API."""
import json
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'evidence/memory-load-20261109'
BASE='http://127.0.0.1:3001'


def main():
    owner=json.loads((ROOT/'infra/runtime/memory-load/accounts.json').read_text(encoding='utf-8'))['owner']
    data=json.loads((EVIDENCE/'dataset.json').read_text(encoding='utf-8'))
    checks=[]
    with httpx.Client(timeout=30,trust_env=False) as client:
        logged=client.post(BASE+'/api/auth/login',json={'email':owner['email'],'password':owner['password']})
        assert logged.status_code==200
        headers={'Authorization':'Bearer '+logged.json()['token']}
        for bucket in ('1d','3d','7d','1m'):
            row=next(r for r in data['rows'] if r['key']==bucket+'-002')
            response=client.get(BASE+'/api/messages/'+row['conversation_id'],headers=headers)
            body=response.json()
            items=body if isinstance(body,list) else body.get('messages',[])
            checks.append(dict(bucket=bucket,http_status=response.status_code,
                source_present=any(i.get('messageId')==row['source_message_id'] for i in items),
                message_count=len(items)))
    (EVIDENCE/'source-api-report.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(checks,ensure_ascii=False,indent=2))
    return 0 if all(c['source_present'] for c in checks) else 1

if __name__=='__main__':
    raise SystemExit(main())
