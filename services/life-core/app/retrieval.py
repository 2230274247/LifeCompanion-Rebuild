"""Pure vector memory retrieval. No keyword overlap, aliases or entity gates.

Every authorized active item is searched. A persistent per-user/model/content
index prevents old memories being silently excluded by an embedding batch cap.
A cold/incomplete index is reported explicitly and prepared in the background.
"""
from __future__ import annotations

import calendar
import hashlib
import httpx
import json
import math
import re
import sqlite3
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .embedding import EmbeddingUnavailable, LocalEmbedding, LocalReranker, MODEL_NAME
from .memory import FORGET, SENSITIVE

_WITHDRAW = re.compile(FORGET.pattern + r"|撤回|不许记|删掉.*记忆|别再提|不要再用.*(?:资料|记忆)")
_ANAPHORA = re.compile(r"这(?:个|件|些|次|事|一)|那(?:个|件|些|次|事|一)|它|他们|后来呢|然后呢|还有呢|当时呢|后来怎么样")
_PROFILE_KEYS = {"drink_preference", "residence", "name", "preferred_name", "occupation",
                 "profession", "language", "timezone", "dietary_preference", "dietary_restriction"}


def _text(item):
    text, value = item.get("canonical_text", ""), item.get("value", "")
    return text + (" " + value if value and value not in text else "")


def _day(query, today):
    """Explicit calendar constraints only; never a content retrieval gate."""
    full = re.search(r"(\d{4})[-年](\d{1,2})[-月](\d{1,2})", query)
    partial = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})日?", query)
    if full:
        return date(*map(int, full.groups()))
    if partial:
        return date(today.year, *map(int, partial.groups()))
    for word, offset in (("大前天", -3), ("三天前", -3), ("3天前", -3),
                         ("前天", -2), ("昨天", -1), ("一天前", -1), ("1天前", -1),
                         ("一周前", -7), ("1周前", -7), ("七天前", -7), ("7天前", -7),
                         ("后天", 2), ("明天", 1), ("今天", 0)):
        if word in query:
            return today + timedelta(days=offset)
    if re.search(r"一个月前|一月前|1个月前", query):
        year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        return date(year, month, min(today.day, calendar.monthrange(year, month)[1]))
    return None


def _content_query(query):
    """Keep explicit calendar metadata out of the semantic representation.

    This removes only a syntactic date span, never topic words or entities.
    Relative temporal language stays intact; _day still constrains all candidates.
    """
    calendar_span = re.compile(r"(?:\d{4}[-年]\d{1,2}[-月]\d{1,2}|(?<!\d)\d{1,2}月\d{1,2})日?(?:那天|当天)?[，,\s]*")
    content = calendar_span.sub("", query, count=1).strip()
    return content or query


_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_NUM = r"(\d+|[一两二三四五六七八九十])"
_RANGE_DAYS = re.compile(rf"(?:近|最近|过去)\s*{_NUM}\s*个?\s*(?:天|日)")
_RANGE_MONTHS = re.compile(rf"(?:近|最近|过去)\s*{_NUM}\s*个?\s*月")
_RANGE_PHRASE = re.compile(
    rf"(?:近|最近|过去)\s*(?:\d+|[一两二三四五六七八九十])\s*个?\s*(?:天|日|月)"
    r"|上(?:个)?月|上月|(?:这个|本)月|上(?:个)?(?:周|星期)|上周|(?:这|本)(?:周|星期)|最近|近期|近来"
)


def _num(text):
    return int(text) if text.isdigit() else _CN_NUM.get(text)


def _months_back(today, n):
    year, month = today.year, today.month - n
    while month <= 0:
        year -= 1
        month += 12
    return date(year, month, min(today.day, calendar.monthrange(year, month)[1]))


def _range(query, today):
    """Temporal window constraint (近N天/近N月/这周/本月/上个月/最近).

    Returns an inclusive (start, end) date pair, or None when the query carries
    no window language. This is metadata, never a content relevance score.
    """
    match = _RANGE_DAYS.search(query)
    if match:
        n = max(1, _num(match.group(1)) or 1)
        return (today - timedelta(days=n - 1), today)
    match = _RANGE_MONTHS.search(query)
    if match:
        n = max(1, _num(match.group(1)) or 1)
        return (_months_back(today, n), today)
    if re.search(r"上(?:个)?月|上月", query):
        start = _months_back(today, 1).replace(day=1)
        return (start, today.replace(day=1) - timedelta(days=1))
    if re.search(r"(?:这个|本)月", query):
        return (today.replace(day=1), today)
    if re.search(r"上(?:个)?(?:周|星期)|上周", query):
        monday = today - timedelta(days=today.weekday())
        return (monday - timedelta(days=7), monday - timedelta(days=1))
    if re.search(r"(?:这|本)(?:周|星期)", query):
        return (today - timedelta(days=today.weekday()), today)
    if re.search(r"最近几[天日]|近几[天日]", query):
        return (today - timedelta(days=3), today)
    if re.search(r"最近|近期|近来", query):
        return (today - timedelta(days=13), today)
    return None


def _item_day(item, zone):
    match = re.match(r"(?:event|plan):(\d{4}-\d{2}-\d{2}):", item.get("semantic_key", ""))
    try:
        if match:
            return date.fromisoformat(match[1])
        if item.get("kind") == "future_plan":
            return None
        stamp = datetime.fromisoformat(item["valid_from"].replace("Z", "+00:00"))
        return stamp.replace(tzinfo=zone).date() if stamp.tzinfo is None else stamp.astimezone(zone).date()
    except (ValueError, TypeError, KeyError):
        return None


def _unit(vector):
    values = tuple(float(value) for value in vector)
    norm = math.sqrt(sum(value * value for value in values))
    if not values or not math.isfinite(norm) or norm == 0:
        raise ValueError("INVALID_EMBEDDING")
    return tuple(value / norm for value in values)


def _confidence(logit):
    logit = float(logit)
    return 1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, logit))))


_QUERY_REWRITE_PROMPT = (
    "你是一名记忆检索改写器。把用户对个人记忆的提问改写成一句自足、具体、适合向量检索的查询短语："
    "展开代词、缩写和抽象请求，指向它们真正想找的具体事实、事件或偏好；只改写、不回答、不臆造，"
    "控制在40字以内。严格返回JSON：{\"query\": \"改写后的查询\"}。"
)


def _rewrite_query(settings, query, cache):
    """Optional LLM pre-step (HyDE-style). Falls back to the original query on
    any failure so a slow or absent LLM never blocks or degrades recall."""
    key = query.strip()
    if not key or not getattr(settings, "memory_llm_key", ""):
        return key
    if cache is not None and key in cache:
        return cache[key]
    try:
        url = getattr(settings, "memory_llm_url", "https://api.deepseek.com/v1").rstrip("/")
        with httpx.Client(timeout=httpx.Timeout(4.0, connect=2.0), trust_env=False) as client:
            response = client.post(
                f"{url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.memory_llm_key}"},
                json={"model": getattr(settings, "memory_llm_model", "deepseek-chat"),
                      "temperature": 0,
                      **getattr(settings, "memory_llm_options", {}),
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": _QUERY_REWRITE_PROMPT},
                                   {"role": "user", "content": query}]})
        if not response.is_success:
            return key
        rewritten = json.loads(response.json()["choices"][0]["message"]["content"]).get("query", "").strip()
        if not rewritten:
            return key
        rewritten = rewritten[:400]
        if cache is not None:
            if len(cache) >= 512:
                cache.clear()
            cache[key] = rewritten
        return rewritten
    except Exception:
        return key


class MemoryRetriever:
    def __init__(self, memory, embedder=None, *, embedding_budget=48,
                 embedding_char_budget=24000, candidate_budget=256, cache_size=1024,
                 semantic_threshold=None, now=None):
        self.memory = memory
        self.embedder = embedder if embedder is not None else LocalEmbedding(
            getattr(memory.settings, "memory_embedding_cache", None),
            getattr(memory.settings, "memory_embedding_model", None))
        self.semantic_threshold = float(semantic_threshold if semantic_threshold is not None else
                                        getattr(memory.settings, "memory_semantic_threshold", 0.58))
        self.reranker = LocalReranker(getattr(memory.settings, "memory_embedding_cache", None))
        self.rerank_enabled = bool(getattr(memory.settings, "memory_rerank_enabled", True))
        self.rerank_candidates = max(8, int(getattr(memory.settings, "memory_rerank_candidates", 32)))
        self.rewrite_enabled = bool(getattr(memory.settings, "memory_query_rewrite_enabled", True))
        self._rewrite_cache = {}
        self._now = now or (lambda zone: datetime.now(zone))
        self._lock = threading.RLock()
        self._index_lock = threading.Lock()
        self._preparing = set()
        # Legacy constructor budgets govern encoding batch size only, never the
        # searchable candidate set. No memory is prefiltered by its text or age.
        self.batch_size = max(1, min(int(embedding_budget), 64))
        with self.memory.store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS memory_vectors (
                user_id TEXT NOT NULL, memory_id TEXT NOT NULL, model TEXT NOT NULL,
                content_hash TEXT NOT NULL, dimension INTEGER NOT NULL, vector TEXT NOT NULL,
                PRIMARY KEY(user_id,memory_id,model))""")

    @property
    def model(self):
        return getattr(self.embedder, "model_name", MODEL_NAME)

    def _key(self, user_id, item):
        return (user_id, item["memory_id"], hashlib.sha256(_text(item).encode()).hexdigest(), self.model)

    def _allowed(self, user_id):
        permissions = self.memory.permissions(user_id)
        if not permissions.get("recall_consent"):
            return []
        sensitive = permissions.get("sensitive_consent", False)
        items = self.memory.list_items(user_id)
        return [item for item in items
                if item.get("user_id") == user_id and item.get("state") == "active" and _text(item)
                and (sensitive or (item.get("sensitivity") == "ordinary" and not SENSITIVE.search(_text(item))))]

    def _purge(self, user_id, allowed=()):
        keep = {item["memory_id"]: self._key(user_id, item)[2] for item in allowed}
        with self.memory.store.connect() as db:
            rows = db.execute("SELECT memory_id,model,content_hash FROM memory_vectors WHERE user_id=?",
                              (user_id,)).fetchall()
            stale = [(user_id, row["memory_id"], row["model"]) for row in rows
                     if keep.get(row["memory_id"]) != row["content_hash"]]
            db.executemany("DELETE FROM memory_vectors WHERE user_id=? AND memory_id=? AND model=?", stale)

    def _vectors(self, user_id, allowed):
        by_id = {item["memory_id"]: item for item in allowed}
        result = {}
        with self.memory.store.connect() as db:
            rows = db.execute("SELECT * FROM memory_vectors WHERE user_id=? AND model=?", (user_id, self.model)).fetchall()
        for row in rows:
            item = by_id.get(row["memory_id"])
            if item is None or row["content_hash"] != self._key(user_id, item)[2]:
                continue
            try:
                vector = _unit(json.loads(row["vector"]))
                if len(vector) == row["dimension"]:
                    result[row["memory_id"]] = vector
            except (ValueError, TypeError):
                continue
        return result

    def warmup(self):
        warm = getattr(self.embedder, "warmup", None)
        status = warm() if warm else "ready"
        if self.rerank_enabled:
            try:
                self.reranker.warmup()
            except Exception:
                pass
        if status == "ready":
            with self.memory.store.connect() as db:
                users = db.execute("SELECT user_id FROM memory_permissions WHERE recall_consent=1").fetchall()
            for row in users:
                try:
                    self.prepare_user(row["user_id"])
                except (EmbeddingUnavailable, ValueError):
                    continue
        return status

    def prepare_user(self, user_id):
        """Build every eligible vector; callers may invoke this after bulk import."""
        with self._index_lock:
            allowed = self._allowed(user_id)
            self._purge(user_id, allowed)
            vectors = self._vectors(user_id, allowed)
            missing = [item for item in allowed if item["memory_id"] not in vectors]
            # Identical content may occur on several dates. Encode once, but retain
            # every independently authorized memory and its own source/date row.
            groups = {}
            for item in missing:
                groups.setdefault(self._key(user_id, item)[2], []).append(item)
            groups = list(groups.values())
            for start in range(0, len(groups), self.batch_size):
                batch = groups[start:start + self.batch_size]
                encoded = list(self.embedder.embed([_text(group[0]) for group in batch]))
                if len(encoded) != len(batch):
                    raise ValueError("INVALID_VECTOR_COUNT")
                # Recheck consent and active/hash state after potentially slow encoding.
                current = {item["memory_id"]: self._key(user_id, item)[2] for item in self._allowed(user_id)}
                writes = []
                for group, raw in zip(batch, encoded):
                    vector = _unit(raw)
                    for item in group:
                        key = self._key(user_id, item)
                        if current.get(item["memory_id"]) == key[2]:
                            writes.append((user_id, item["memory_id"], self.model, key[2], len(vector), json.dumps(vector)))
                with self.memory.store.connect() as db:
                    db.executemany("INSERT OR REPLACE INTO memory_vectors VALUES (?,?,?,?,?,?)", writes)
            return len(self._vectors(user_id, self._allowed(user_id)))

    def _schedule(self, user_id):
        with self._lock:
            if user_id in self._preparing:
                return
            self._preparing.add(user_id)
        def work():
            try:
                self.prepare_user(user_id)
            except Exception:
                # Query status exposes index_not_ready; never fake a successful lookup.
                pass
            finally:
                with self._lock:
                    self._preparing.discard(user_id)
        threading.Thread(target=work, name="memory-vector-index", daemon=True).start()

    def _recent_hits(self, user_id, conversation_id, allowed, now):
        if not conversation_id:
            return []
        with self.memory.store.connect() as db:
            rows = db.execute("""SELECT memory_id,message_id,created_at FROM memory_recall_hits
                WHERE user_id=? AND conversation_id=? ORDER BY created_at DESC LIMIT 16""",
                (user_id, conversation_id)).fetchall()
        ids, latest = [], None
        for row in rows:
            try:
                stamp = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                if stamp.tzinfo is None or not now - timedelta(hours=2) <= stamp <= now:
                    continue
            except ValueError:
                continue
            latest = latest or row["message_id"]
            if row["message_id"] == latest and row["memory_id"] in allowed:
                ids.append(allowed[row["memory_id"]])
        return ids

    def overview(self, user_id, *, window=None, today=None, limit=20, offset=0, zone=None):
        """List what happened in a period without requiring a content relevance score.

        Each event and dated source is included by its occurrence day, never by how
        similar it is to the word 'interesting'. Undated sources are reported but never
        assigned a date, so they cannot masquerade as events on the wrong day.
        """
        meta = dict(mode="overview", start=None, end=None, returned=0, truncated=False,
                    has_more=False, undated_count=0, total_count=0)
        result = dict(status="no_match", items=[], retrieval=meta)
        if not self.memory.permissions(user_id).get("recall_consent"):
            self._purge(user_id)
            result["status"] = meta["semantic_status"] = "permission_denied"
            return result
        zone = zone or ZoneInfo(self.memory.timezone(user_id))
        today = today or self._now(zone).date()
        start, end = (window[0], window[1]) if window else (today - timedelta(days=13), today)
        meta.update(start=start.isoformat(), end=end.isoformat())
        allowed = self._allowed(user_id)
        sources = self.memory.sources.items(user_id) if hasattr(self.memory, "sources") else []
        dated, undated = [], []
        for item in allowed:
            day = _item_day(item, zone)
            (dated if day is not None and start <= day <= end else undated).append(item)
        # A source quote is the message timestamp, not an event occurrence day,
        # so it is reported separately and never placed on an event timeline.
        undated.extend(sources)
        dated.sort(key=lambda item: _item_day(item, zone))
        undated.sort(key=lambda item: (item.get("recorded_at") or item.get("created_at") or ""))
        total = len(dated) + len(undated)
        page = dated[offset:offset + limit]
        result["items"] = page
        result["status"] = "matched" if page else "no_match"
        meta.update(returned=len(page), total_count=total,
                    truncated=offset + len(page) < len(dated),
                    has_more=offset + len(page) < len(dated), undated_count=len(undated))
        return result

    def retrieve(self, user_id, query, recent_messages=None, conversation_id=None):
        meta = dict(mode="semantic_only", model=self.model, threshold=self.semantic_threshold,
                    semantic_status="not_used", context_source="none", context_used=False,
                    candidate_count=0, semantic_candidates=0, embedded_count=0, cache_hits=0,
                    budget_exhausted=False, profile_match_ids=[], keyword_retrieval=False,
                    dedup_dropped=0, rerank_used=False, rerank_pool=0, query_rewritten=False)
        result = dict(status="no_match", items=[], profile=[], retrieval=meta)
        if not self.memory.permissions(user_id).get("recall_consent"):
            self._purge(user_id)
            result["status"] = meta["semantic_status"] = "permission_denied"
            return result
        if not query.strip():
            result["status"], meta["semantic_status"] = "empty_input", "empty_query"
            return result
        if _WITHDRAW.search(query):
            result["status"], meta["semantic_status"] = "excluded", "explicit_withdrawal"
            return result
        sensitive = self.memory.permissions(user_id).get("sensitive_consent", False)
        if not sensitive and SENSITIVE.search(query):
            meta["semantic_status"] = "sensitive_query_blocked"
            return result
        allowed = self._allowed(user_id)
        self._purge(user_id, allowed)
        recent = [m.get("text", m.get("content", "")) for m in (recent_messages or [])
                  if isinstance(m, dict) and m.get("role") == "user"][-4:]
        recent = [s for s in recent if isinstance(s, str) and s.strip()]
        if any(_WITHDRAW.search(text) for text in recent):
            result["status"], meta["semantic_status"] = "excluded", "context_withdrawal"
            return result
        recent = [s[:500] for s in recent if sensitive or not SENSITIVE.search(s)]
        zone = ZoneInfo(self.memory.timezone(user_id))
        now = self._now(zone)
        try:
            requested = _day(query, now.date())
        except ValueError:
            meta["semantic_status"] = "invalid_date"
            return result
        span = _range(query, now.date())
        search = _content_query(query) if requested is not None else query
        if span is not None:
            search = _RANGE_PHRASE.sub("", search, count=1).strip() or search
        search = search[:2000]
        if self.rewrite_enabled and not _ANAPHORA.search(query):
            rewritten = _rewrite_query(self.memory.settings, search, self._rewrite_cache)
            if rewritten != search:
                search = rewritten[:2000]
                meta["query_rewritten"] = True
        if _ANAPHORA.search(query):
            if recent:
                search = recent[-1] + "\n" + search[:1000]
                meta.update(context_source="recent_users", context_used=True)
            else:
                hits = self._recent_hits(user_id, conversation_id, {i["memory_id"]: i for i in allowed}, now)
                if len(hits) == 1:
                    search = _text(hits[0]) + "\n" + search[:1000]
                    meta.update(context_source="recall_hits", context_used=True)
                else:
                    meta["context_source"] = "ambiguous"
                    return result
        profile = [i for i in allowed if i["kind"] == "stable_fact" and i["semantic_key"].removeprefix("fact:") in _PROFILE_KEYS]
        if span is not None:
            start, end = span
            candidates = [i for i in allowed
                          if (day := _item_day(i, zone)) is not None and start <= day <= end]
        elif requested is not None:
            candidates = [i for i in allowed if _item_day(i, zone) == requested]
        else:
            candidates = list(allowed)
        vectors = self._vectors(user_id, allowed)
        meta.update(candidate_count=len(candidates), indexed_count=len(vectors), total_count=len(allowed))
        if getattr(self.embedder, "status", "ready") != "ready":
            meta["semantic_status"] = getattr(self.embedder, "status", "unavailable")
            result["status"] = "unavailable"
            return result
        if len(vectors) != len(allowed):
            self._schedule(user_id)
            meta["semantic_status"], result["status"] = "index_not_ready", "unavailable"
            return result
        try:
            encode = getattr(self.embedder, "query_embed", self.embedder.embed)
            query_vector = _unit(list(encode([search]))[0])
        except (EmbeddingUnavailable, ValueError, IndexError):
            meta["semantic_status"], result["status"] = "embedding_unavailable", "unavailable"
            return result
        scored = []
        for item in candidates:
            vector = vectors.get(item["memory_id"])
            if vector is None or len(vector) != len(query_vector):
                meta["semantic_status"], result["status"] = "dimension_mismatch", "unavailable"
                return result
            score = sum(a * b for a, b in zip(query_vector, vector))
            if score >= self.semantic_threshold:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["memory_id"]))
        if (self.rerank_enabled and self.reranker.status == "ready" and len(scored) > 1):
            head, tail = scored[:self.rerank_candidates], scored[self.rerank_candidates:]
            try:
                logits = self.reranker.rerank(search, [_text(item) for _, item in head])
                if len(logits) == len(head):
                    reranked = sorted(
                        ((_confidence(logit), item) for (_, item), logit in zip(head, logits)),
                        key=lambda pair: (-pair[0], pair[1]["memory_id"]))
                    scored = reranked + tail
                    meta["rerank_used"] = True
                    meta["rerank_pool"] = len(head)
            except Exception:
                pass
        deduped = []
        seen_hashes = set()
        for score, item in scored:
            digest = self._key(user_id, item)[2]
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            deduped.append((score, item))
        meta["dedup_dropped"] = len(scored) - len(deduped)
        scored = deduped
        result["items"] = [item for _, item in scored[:8] if item not in profile]
        # A profile is an explicitly bounded background, separately labelled.
        # It is not reported as a semantic hit unless it passes the vector threshold.
        profile_ids = {i["memory_id"] for i in profile}
        relevant_profile = [item for _, item in scored if item["memory_id"] in profile_ids]
        chosen = relevant_profile + [i for i in profile if i not in relevant_profile]
        chars = 0
        for item in chosen:
            size = len(_text(item))
            if len(result["profile"]) < 4 and chars + size <= 1200:
                result["profile"].append(item)
                chars += size
        meta.update(semantic_status="ready", semantic_candidates=len(candidates), cache_hits=len(candidates),
                    profile_match_ids=[i["memory_id"] for i in relevant_profile])
        meta["top_scores"] = [round(score, 4) for score, _ in scored[:8]]
        result["status"] = "matched" if result["items"] or result["profile"] else "no_match"
        return result
