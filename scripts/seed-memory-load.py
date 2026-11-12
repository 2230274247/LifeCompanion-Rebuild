"""Force-import synthetic history without reading service credentials or token maps.

Uses ordinary registration/login for fresh test users, then the authorized local
system-import path. Selected memory events remain pending until real Memos
publication can be verified. Never fakes memo refs or published status.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, UTC
from pathlib import Path
from zoneinfo import ZoneInfo
import secrets
import httpx

ROOT = Path(__file__).resolve().parents[1]
INSTALL = Path('H:/AI For research institute/LifeCompanion-Rebuild')
RUNTIME = ROOT / 'infra/runtime/memory-load'
EVIDENCE = ROOT / 'evidence/memory-load-20261109'
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'services/life-core')]
from memory_load_dataset import build_dataset
from app.config import Settings
from app.store import Store
from app.memory import MemoryService, Candidate
from app.retrieval import MemoryRetriever


def settings():
    return Settings(database_path=INSTALL / 'services/life-core/data/life-core.sqlite3',
                    internal_token='',jwt_secret='',jwt_refresh_secret='',
                    memos_base_url='http://127.0.0.1:5230',memos_api_token='',
                    timezone='Asia/Hong_Kong',allowed_origins=('http://localhost:3001',),
                    memory_embedding_cache=str(ROOT / 'services/life-core/data/embedding-models'))


def checked(response):
    if response.status_code != 200:
        raise RuntimeError(f'HTTP_{response.status_code}')
    return response.json()


def register(client, label):
    suffix = secrets.token_hex(5)
    account = dict(username=f'memory-load-{label}-{suffix}', name='合成记忆验收·'+label,
                   email=f'memory-load-{label}-{suffix}@example.test', password=secrets.token_urlsafe(24)+'aA1!')
    checked(client.post('http://127.0.0.1:3001/api/auth/register',
                        json={**account, 'confirm_password': account['password']}))
    login = checked(client.post('http://127.0.0.1:3001/api/auth/login',
                                json={'email': account['email'], 'password': account['password']}))
    account.update(librechat_user_id=login['user']['id'], token=login['token'])
    return account


def other_counts(store, owners):
    with store.connect() as db:
        rows = db.execute('SELECT user_id,COUNT(*) FROM memory_items GROUP BY user_id').fetchall()
    return {r[0]: r[1] for r in rows if r[0] not in owners}


def seed_chat_sources(account, rows):
    payload = dict(uid=account['librechat_user_id'], messages=rows)
    input_file = RUNTIME / 'chat-sources.json'
    input_file.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    container_file = '/tmp/memory-load-'+account['librechat_user_id']+'.json'
    subprocess.run(['docker','cp',str(input_file),'lifecompanion-mongo:'+container_file],check=True,capture_output=True)
    code = "const inputPath="+json.dumps(container_file)+";"+"""const fs=require('fs'); const p=JSON.parse(fs.readFileSync(inputPath,'utf8'));
    if(!p.messages.every(x=>x.synthetic===true)){throw Error('NOT_SYNTHETIC')}
    const d=db.getSiblingDB('LibreChat');
    for(const r of p.messages){
      const stamp=new Date(r.occurred_at);
      d.messages.updateOne({messageId:r.source_message_id,user:p.uid},{$setOnInsert:{
        messageId:r.source_message_id,conversationId:r.conversation_id,user:p.uid,
        text:r.text,isCreatedByUser:true,sender:'User',parentMessageId:'00000000-0000-0000-0000-000000000000',
        createdAt:stamp,updatedAt:stamp}},{upsert:true});
      d.conversations.updateOne({conversationId:r.conversation_id,user:p.uid},{$setOnInsert:{
        conversationId:r.conversation_id,user:p.uid,title:'合成历史·'+r.source_window,
        messages:[],createdAt:stamp,updatedAt:stamp},$set:{
        endpoint:'DeepSeek',endpointType:'custom',model:'deepseek-chat'}},{upsert:true});
    } print('SYNTHETIC_CHAT_SOURCES_OK');"""
    result = subprocess.run(['docker','exec','lifecompanion-mongo','mongosh','--quiet','--eval',code],
                            capture_output=True,timeout=90)
    if result.returncode:
        raise RuntimeError('SYNTHETIC_CHAT_IMPORT_FAILED: '+(result.stderr+result.stdout).decode('utf-8','replace')[:600])


def main():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    cfg = settings()
    store = Store(cfg.database_path)
    backup = RUNTIME / ('before-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%S')+'.sqlite3')
    with sqlite3.connect(cfg.database_path.resolve().as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    state_path = RUNTIME / 'accounts.json'
    with httpx.Client(timeout=45, trust_env=False) as client:
        if state_path.exists():
            accounts = json.loads(state_path.read_text(encoding='utf-8'))
        else:
            accounts = {'owner':register(client,'owner'), 'outsider':register(client,'outsider')}
            state_path.write_text(json.dumps(accounts,ensure_ascii=False,indent=2),encoding='utf-8')
    for account in accounts.values():
        profile = store.bootstrap_user(librechat_user_id=account['librechat_user_id'],
            memos_user_id='users/'+account['username'],memos_username=account['username'],
            display_name=account['name'],memory_consent=True,image_consent=False)
        account['life_user_id'] = profile['life_user_id']
    state_path.write_text(json.dumps(accounts,ensure_ascii=False,indent=2),encoding='utf-8')
    before = other_counts(store, {a['life_user_id'] for a in accounts.values()})
    memory = MemoryService(store,cfg)
    memory.initialize()
    for account in accounts.values():
        memory.set_permissions(account['life_user_id'], {'recall_consent':True,'sensitive_consent':True})
    today = datetime.now(ZoneInfo(cfg.timezone))
    rows, questions = build_dataset(today)
    namespace = uuid.UUID('72ed663a-8ca4-4e70-a09a-6fcc40ae193b')
    owner = accounts['owner']
    for index, row in enumerate(rows):
        source = str(uuid.uuid5(namespace,owner['librechat_user_id']+':'+row['key']))
        conversation = str(uuid.uuid5(namespace,owner['librechat_user_id']+':'+row['source_window']))
        stamp = datetime.fromisoformat(row['occurred_at'])
        event = store.create_event(user_id=owner['life_user_id'],source_type='chat',source_message_ids=[source],
            conversation_id=conversation,occurred_at=row['occurred_at'],title='[合成] '+row['title'],
            summary='[合成验收资料] '+row['text'],confidence=1,consent_state='granted',status='pending',
            idempotency_key=owner['life_user_id']+':forced-history:'+row['key'])
        candidate = Candidate(candidate_type='life_event',canonical_text=row['text'],evidence_quote=row['text'],
                              occurred_state='occurred',confidence=1,sensitivity='ordinary',image_candidate=True)
        candidate._classifier = 'synthetic:forced-history:v1'
        item = memory.save(owner['life_user_id'],candidate,memory.key_for(candidate,row['text'],stamp,cfg.timezone),
                           source,conversation,row['text'],stamp,event['event_id'])
        with store.connect() as db:
            db.execute('UPDATE memory_items SET created_at=?,updated_at=?,importance=? WHERE memory_id=? AND user_id=?',
                       (row['occurred_at'],row['occurred_at'],0.9 if row['selected_for_publication'] else 0.5,item['memory_id'],owner['life_user_id']))
            db.execute('UPDATE events SET created_at=?,updated_at=? WHERE event_id=? AND user_id=?',
                       (row['occurred_at'],row['occurred_at'],event['event_id'],owner['life_user_id']))
        row.update(memory_id=item['memory_id'],event_id=event['event_id'],source_message_id=source,
                   conversation_id=conversation,synthetic=True,publication_status='pending')
        if index % 100 == 99:
            print(f'IMPORTED {index+1}/400',flush=True)
    seed_chat_sources(owner,rows)
    retriever = MemoryRetriever(memory)
    if retriever.embedder.warmup() != 'ready':
        raise RuntimeError('LOCAL_VECTOR_MODEL_NOT_READY')
    count = retriever.prepare_user(owner['life_user_id'])
    after = other_counts(store, {a['life_user_id'] for a in accounts.values()})
    assert before == after, 'OTHER_USERS_CHANGED'
    manifest = dict(created_at=today.isoformat(),total=len(rows),indexed=count,
                    selected=sum(r['selected_for_publication'] for r in rows),published=0,
                    publication_status='BLOCKED_SERVICE_CREDENTIAL_REVIEW',
                    buckets={b:sum(r['bucket']==b for r in rows) for b in ('1d','3d','7d','1m')},
                    other_users_unchanged=True,rows=rows,questions=questions)
    (EVIDENCE/'dataset.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'SEEDED total={len(rows)} vectors={count} selected={manifest["selected"]} publication=PENDING other_users_unchanged=True',flush=True)

if __name__=='__main__':
    main()
