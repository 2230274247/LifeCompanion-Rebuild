"""Verify the retrieval optimizations against the real DB + real local models.

Copies the product DB into the gitignored runtime dir first, so the product
database and the running service are never touched. Exercises date-range
parsing, content dedup and the cross-encoder reranker on the two queries the
user reported failing. Query rewrite stays gracefully off without an LLM key.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
INSTALL = Path('H:/AI For research institute/LifeCompanion-Rebuild')
RUNTIME = ROOT / 'infra/runtime/memory-load'
sys.path[:0] = [str(ROOT / 'services/life-core')]

from app.config import Settings
from app.store import Store
from app.memory import MemoryService
from app.retrieval import MemoryRetriever, _range, _day

OWNER = 'life_c91717eedf15e3adc63f'
PRODUCT_DB = INSTALL / 'services/life-core/data/life-core.sqlite3'
VERIFY_DB = RUNTIME / 'verify-optimize.sqlite3'
CACHE = ROOT / 'services/life-core/data/embedding-models'
TIMEZONE = 'Asia/Hong_Kong'


def settings(db):
    return Settings(database_path=db, internal_token='', jwt_secret='', jwt_refresh_secret='',
                    memos_base_url='http://127.0.0.1:5230', memos_api_token='',
                    timezone=TIMEZONE, allowed_origins=('http://localhost:3001',),
                    memory_embedding_cache=str(CACHE))


def main():
    shutil.copy2(PRODUCT_DB, VERIFY_DB)
    cfg = settings(VERIFY_DB)
    store = Store(VERIFY_DB)
    memory = MemoryService(store, cfg)
    memory.initialize()
    r = MemoryRetriever(memory)

    print('embedder warmup:', r.embedder.warmup(), flush=True)
    print('reranker warmup:', r.reranker.warmup(), flush=True)
    print('reranker status:', r.reranker.status, flush=True)
    print('owner vectors:', r.prepare_user(OWNER), flush=True)

    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    queries = ['总结老师提醒我注意什么', '近15天的日程', '近一个月的日程']
    for q in queries:
        got = r.retrieve(OWNER, q)
        meta = got['retrieval']
        print('=' * 72, flush=True)
        print(f'QUERY: {q}', flush=True)
        print(f'  _day={_day(q, today)}  _range={_range(q, today)}', flush=True)
        print(f'  status={got["status"]}  candidates={meta["candidate_count"]}'
              f'  dedup_dropped={meta["dedup_dropped"]}  rerank_used={meta["rerank_used"]}'
              f'  rerank_pool={meta["rerank_pool"]}  query_rewritten={meta["query_rewritten"]}', flush=True)
        scores = meta.get('top_scores', [])
        for idx, item in enumerate(got['items']):
            score = scores[idx] if idx < len(scores) else None
            date = item.get('semantic_key', '') or item.get('valid_from', '')
            print(f'  [{idx}] {score}  {date}  {item.get("canonical_text", "")[:46]}', flush=True)


if __name__ == '__main__':
    main()
