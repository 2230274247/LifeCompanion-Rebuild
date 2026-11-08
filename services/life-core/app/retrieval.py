"""Permission-first hybrid memory retrieval; no writes to the memory store.

MemoryRetriever(memory, embedder=None).retrieve(user_id, query,
    recent_messages=None, conversation_id=None) returns original memory_items in
separate items/profile lists. Inject an embedder with embed(list[str]) (and
optionally query_embed) for tests. Start warmup() in a background startup worker;
retrieve() never loads the local model. Vector caches are bounded, process-local,
and purged against the current authorized active snapshot on every request.
"""
from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import threading
from collections import OrderedDict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .embedding import EmbeddingUnavailable, LocalEmbedding, MODEL_NAME
from .memory import FORGET, SENSITIVE, normalized


_WITHDRAW = re.compile(FORGET.pattern + r"|撤回|不许记|删掉.*记忆|别再提|不要再用.*(?:资料|记忆)")
_ANAPHORA = re.compile(r"这(?:个|件|些|次|事|一)|那(?:个|件|些|次|事|一)|它|他们|后来呢|然后呢|还有呢|当时呢|后来怎么样")
_STOP = re.compile(
    r"一直想|怎么样|怎么回事|发生什么|什么时候|为什么|哪些|什么|怎么|是否|记不记得|记得|"
    r"帮我|告诉我|聊过|聊到|说过|提过|谈到|关于|有关|最近|刚才|之前|以前|过去|上次|后来|然后|当时|"
    r"谢谢|好的|知道了|你好|继续|请问|嗯|和|与|以及|"
    r"大前天|前天|昨天|今天|明天|后天|加入了|加入|参加了|参加|这个|那个|这件|那件|"
    r"平常|平时|通常|最喜欢|喜欢|准备|打算|计划去|我|你|他|它|的|了|吗|呢|啊|吧|很|是|在|有|过|还|要"
)
_SUFFIXES = ("项目组", "项目", "团队", "公司", "大学", "实验室", "公园")
_GENERIC = {"项目", "项目组", "团队", "事情", "东西", "物品", "情况", "后续", "进展", "记忆", "回忆"}
_ALIASES = (("散步", "遛弯", "漫步"), ("开心", "高兴", "愉快"),
            ("项目组", "团队"), ("居住", "住处", "城市"), ("饮品", "喝茶", "茶"))
_PROFILE_KEYS = {"drink_preference", "residence", "name", "preferred_name", "occupation",
                 "profession", "language", "timezone", "dietary_preference", "dietary_restriction"}


def _chunks(text):
    text = re.sub(r"\d{4}[-年]\d{1,2}[-月]\d{1,2}日?|\d{1,2}月\d{1,2}日?", " ", text)
    return re.findall(r"[a-z0-9][a-z0-9_-]*[一-鿿]*|[一-鿿]+", _STOP.sub(" ", text.casefold()))


def _grams(text):
    result = set()
    for chunk in _chunks(text):
        if len(chunk) < 2:
            continue
        result.add(chunk)
        result.update(chunk[i:i + 2] for i in range(len(chunk) - 1))
    return result


def _entities(text):
    result = set()
    for chunk in _chunks(text):
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]+", chunk):
            result.add(normalized(chunk))
        else:
            pattern = r"[一-鿿]{2,24}?(?:" + "|".join(_SUFFIXES) + ")"
            result.update(re.findall(pattern, chunk))
    # Quoted names are useful even without a recognized entity suffix.
    result.update(normalized(m) for m in re.findall(r"[“「\"]([^”」\"]{2,30})[”」\"]", text))
    return result


def _expand(text):
    additions = []
    for group in _ALIASES:
        if any(word in text for word in group):
            additions.extend(group)
    return text + " " + " ".join(additions)


def _text(item):
    text = item.get("canonical_text", "")
    value = item.get("value", "")
    return text + (" " + value if value and value not in text else "")


def _day(query, today):
    full = re.search(r"(\d{4})[-年](\d{1,2})[-月](\d{1,2})", query)
    partial = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})日?", query)
    if full:
        return date(*map(int, full.groups()))
    if partial:
        return date(today.year, *map(int, partial.groups()))
    for word, offset in (("大前天", -3), ("前天", -2), ("昨天", -1), ("后天", 2), ("明天", 1), ("今天", 0)):
        if word in query:
            return today + timedelta(days=offset)
    return None


def _item_day(item, zone):
    match = re.match(r"(?:event|plan):(\d{4}-\d{2}-\d{2}):", item.get("semantic_key", ""))
    try:
        if match:
            return date.fromisoformat(match[1])
        # Unspecified plan dates must not be interpreted as their creation date.
        if item.get("kind") == "future_plan":
            return None
        stamp = datetime.fromisoformat(item["valid_from"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=zone)
        return stamp.astimezone(zone).date()
    except (ValueError, TypeError, KeyError):
        return None


def _unit(vector):
    values = tuple(float(value) for value in vector)
    norm = math.sqrt(sum(value * value for value in values))
    if not values or not math.isfinite(norm) or norm == 0:
        raise ValueError("invalid embedding")
    return tuple(value / norm for value in values)


class MemoryRetriever:
    def __init__(self, memory, embedder=None, *, embedding_budget=48,
                 embedding_char_budget=24000, candidate_budget=256,
                 cache_size=1024, semantic_threshold=0.68, now=None):
        self.memory = memory
        self.embedder = embedder if embedder is not None else LocalEmbedding(
            getattr(memory.settings, "memory_embedding_cache", None))
        self.embedding_budget = max(0, min(int(embedding_budget), 256))
        self.embedding_char_budget = max(0, min(int(embedding_char_budget), 128000))
        self.candidate_budget = max(1, min(int(candidate_budget), 2048))
        self.cache_size = max(0, min(int(cache_size), 8192))
        self.semantic_threshold = max(0.0, min(float(semantic_threshold), 1.0))
        self._now = now or (lambda zone: datetime.now(zone))
        self._cache = OrderedDict()
        self._lock = threading.RLock()

    def warmup(self):
        """Explicit startup hook. Schedule this in a background worker."""
        warmup = getattr(self.embedder, "warmup", None)
        return warmup() if warmup else "ready"

    def _key(self, user_id, item):
        model = getattr(self.embedder, "model_name", MODEL_NAME)
        return (user_id, item["memory_id"], hashlib.sha256(_text(item).encode()).hexdigest(), model)

    def _purge(self, user_id, allowed=()):
        keep = {self._key(user_id, item) for item in allowed}
        for key in list(self._cache):
            if key[0] == user_id and key not in keep:
                del self._cache[key]

    def _hits(self, user_id, conversation_id, allowed, now):
        if not conversation_id:
            return []
        cutoff = (now - timedelta(hours=2)).timestamp()
        try:
            with self.memory.store.connect() as db:
                rows = db.execute("""SELECT memory_id,message_id,created_at FROM memory_recall_hits
                    WHERE user_id=? AND conversation_id=?
                    ORDER BY created_at DESC,message_id DESC,memory_id LIMIT 32""",
                    (user_id, conversation_id)).fetchall()
        except (AttributeError, sqlite3.OperationalError):
            return []
        latest_message = None
        hits = []
        for row in rows:
            try:
                stamp = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                if stamp.tzinfo is None or not cutoff <= stamp.timestamp() <= now.timestamp():
                    continue
            except (ValueError, TypeError):
                continue
            if latest_message is None:
                latest_message = row["message_id"]
            if row["message_id"] != latest_message:
                continue
            item = allowed.get(row["memory_id"])
            if item and item.get("kind") == "life_event":
                hits.append(item)
        return hits

    def _context(self, query, recent, hits):
        if not _ANAPHORA.search(query):
            return query, set(), "none", False
        explicit = _entities(query)
        if explicit:
            return query, explicit, "none", False
        topic = "项目" if "项目" in query or "团队" in query else None
        for text in reversed(recent):
            if _WITHDRAW.search(text) or _ANAPHORA.search(text) or not _grams(text):
                continue
            if topic and not re.search(r"项目|团队", text):
                continue
            useful = set(_chunks(text)) - _GENERIC
            if not useful:
                continue
            # Only the nearest relevant user topic is carried over, within four turns.
            entities = _entities(text)
            if len(entities) > 1:
                return query, set(), "ambiguous", True
            related = [t for t in recent if t != text and entities & _entities(t) and not _WITHDRAW.search(t)]
            return query + " " + " ".join((related + [text])[-4:]), entities, "recent_users", False
        if topic:
            hits = [item for item in hits if re.search(r"项目|团队", _text(item))]
        groups = {tuple(sorted(_entities(_text(item)))) or (item["memory_id"],) for item in hits}
        if len(groups) == 1:
            text = _text(hits[0])
            return query + " " + text, _entities(text), "recall_hits", False
        return query, set(), "ambiguous", True

    def _lexical(self, query, item):
        text = _text(item)
        query_grams, text_grams = _grams(_expand(query)), _grams(_expand(text))
        overlap = len(query_grams & text_grams)
        exact = any(chunk in text.casefold() for chunk in _chunks(query) if len(chunk) >= 2)
        score = 0.0
        if overlap and (overlap >= 2 or exact):
            score = 0.45 * overlap / max(1, len(query_grams)) + 0.25 * min(1, overlap / 3)
        entities = _entities(query)
        if any(entity in normalized(text) for entity in entities):
            score += 0.8
        return score

    def _semantic(self, user_id, query, candidates, metadata):
        status = getattr(self.embedder, "status", "ready")
        if status != "ready":
            metadata["semantic_status"] = status
            return {}
        if not candidates:
            metadata["semantic_status"] = "no_candidates"
            return {}
        if not self.embedding_budget or len(query) + 1 > self.embedding_char_budget:
            metadata.update(semantic_status="budget_exhausted", budget_exhausted=True)
            return {}
        chosen, missing, used_chars = [], [], len(query)
        for item in candidates:
            key = self._key(user_id, item)
            if key in self._cache:
                chosen.append((item, key))
                self._cache.move_to_end(key)
                continue
            text = _text(item)
            if len(missing) >= self.embedding_budget or used_chars + len(text) > self.embedding_char_budget:
                metadata["budget_exhausted"] = True
                continue
            chosen.append((item, key))
            missing.append((key, text))
            used_chars += len(text)
        if not chosen:
            metadata["semantic_status"] = "budget_exhausted"
            return {}
        try:
            query_encoder = getattr(self.embedder, "query_embed", self.embedder.embed)
            query_rows = list(query_encoder([query]))
            if len(query_rows) != 1:
                raise ValueError("invalid query embedding count")
            query_vector = _unit(query_rows[0])
            pending = {}
            if missing:
                rows = list(self.embedder.embed([text for _, text in missing]))
                if len(rows) != len(missing):
                    raise ValueError("invalid document embedding count")
                pending = {key: _unit(row) for (key, _), row in zip(missing, rows)}
            vectors = {key: pending[key] if key in pending else self._cache[key] for _, key in chosen}
            if any(len(vector) != len(query_vector) for vector in vectors.values()):
                raise ValueError("embedding dimension mismatch")
            scores = {item["memory_id"]: sum(a * b for a, b in zip(query_vector, vectors[key]))
                      for item, key in chosen}
            metadata.update(semantic_status="ready", semantic_candidates=len(chosen),
                            embedded_count=len(missing), cache_hits=len(chosen) - len(missing))
            for key, vector in pending.items():
                self._cache[key] = vector
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
            return scores
        except EmbeddingUnavailable as error:
            metadata["semantic_status"] = str(error)
        except Exception:
            metadata["semantic_status"] = "embedding_failed"
        return {}

    def retrieve(self, user_id, query, recent_messages=None, conversation_id=None):
        # The lock also serializes injected embedders and protects LRU mutations.
        with self._lock:
            return self._retrieve(user_id, query, recent_messages, conversation_id)

    def _retrieve(self, user_id, query, recent_messages, conversation_id):
        meta = dict(mode="keyword_entity", semantic_status="not_used", context_source="none",
                    context_used=False, candidate_count=0, semantic_candidates=0,
                    embedded_count=0, cache_hits=0, budget_exhausted=False, profile_match_ids=[])
        result = dict(status="no_match", items=[], profile=[], retrieval=meta)
        permission = self.memory.permissions(user_id)
        if not permission.get("recall_consent"):
            self._purge(user_id)
            result["status"], meta["semantic_status"] = "permission_denied", "permission_denied"
            return result
        if not query.strip():
            self._purge(user_id)
            result["status"], meta["semantic_status"] = "empty_input", "empty_query"
            return result
        if _WITHDRAW.search(query):
            self._purge(user_id)
            result["status"], meta["semantic_status"] = "excluded", "explicit_withdrawal"
            return result
        recent = []
        for message in recent_messages or []:
            if isinstance(message, dict) and message.get("role") == "user":
                text = message.get("content", message.get("text", ""))
                if isinstance(text, str) and text.strip() and text.strip() != query.strip():
                    recent.append(text)
        recent = recent[-4:]
        withdrawals = [text for text in recent if _WITHDRAW.search(text)]
        sensitive = permission.get("sensitive_consent", False)
        # Never encode sensitive query/context text without the corresponding consent.
        query_sensitive = not sensitive and bool(SENSITIVE.search(query))
        recent = [text for text in recent if sensitive or not SENSITIVE.search(text)]
        allowed = [item for item in self.memory.list_items(user_id)
                   if item.get("user_id") == user_id and item.get("state") == "active"
                   and item.get("canonical_text")
                   and (sensitive or (item.get("sensitivity") == "ordinary" and not SENSITIVE.search(_text(item))))]
        for text in withdrawals:
            # A referential withdrawal cannot safely identify just one item here.
            if _ANAPHORA.search(text) or not _grams(_WITHDRAW.sub(" ", text)):
                allowed = []
                break
            allowed = [item for item in allowed if self._lexical(_WITHDRAW.sub(" ", text), item) < 0.25]
        self._purge(user_id, allowed)
        zone = ZoneInfo(self.memory.timezone(user_id))
        now = self._now(zone)
        today = now.astimezone(zone).date()
        try:
            requested_day = _day(query, today)
        except ValueError:
            meta["semantic_status"] = "invalid_date"
            return result
        past = bool(re.search(r"昨天|前天|以前|之前|过去|上次|当时|曾经", query)) or bool(requested_day and requested_day < today)
        hits = self._hits(user_id, conversation_id, {item["memory_id"]: item for item in allowed}, now)
        context_recent = [text[:1000] for text in recent if not _WITHDRAW.search(text)]
        search, entities, context_source, ambiguous = self._context(query, context_recent, hits)
        meta.update(context_source=context_source, context_used=context_source in ("recent_users", "recall_hits"))
        # Keep the query embedding bounded even with long incoming messages.
        search = search[:2000]
        query_entities = entities or _entities(query)
        meaningful = bool(_grams(_expand(search)) or requested_day or re.search(r"带|东西|物品", query))
        ambiguous = ambiguous or not meaningful
        hit_ids = {item["memory_id"] for item in hits}
        time_only = not _grams(re.sub(r"发生|经历|做过|做了|事情|回忆|记忆|事儿|干了|干过|做什么|干什么", " ", query))
        ranked = []
        for item in allowed:
            if item["kind"] == "stable_fact" and item.get("semantic_key", "").removeprefix("fact:") in _PROFILE_KEYS:
                continue
            if item["kind"] not in ("life_event", "future_plan", "stable_fact") or ambiguous:
                continue
            if item["kind"] == "future_plan" and past:
                continue
            if requested_day and _item_day(item, zone) != requested_day:
                continue
            if query_entities and not any(entity in normalized(_text(item)) for entity in query_entities):
                continue
            if context_source == "recall_hits" and not entities and item["memory_id"] not in hit_ids:
                continue
            score = self._lexical(search, item)
            if requested_day and (time_only or score >= 0.25):
                score += 0.4
            if item["kind"] == "future_plan" and re.search(r"带|东西|物品|除了|还有", query):
                score += 0.4
            ranked.append((score, item))
        ranked.sort(key=lambda pair: (pair[0], pair[1].get("updated_at", ""), pair[1]["memory_id"]), reverse=True)
        meta["candidate_count"] = len(ranked)
        meta["budget_exhausted"] = len(ranked) > self.candidate_budget
        ranked = ranked[:self.candidate_budget]
        if query_sensitive:
            meta["semantic_status"] = "sensitive_query_blocked"
            similarities = {}
        else:
            similarities = self._semantic(user_id, search, [item for _, item in ranked], meta)
        if meta["semantic_status"] == "ready":
            meta["mode"] = "hybrid"
        scored = []
        for lexical, item in ranked:
            similarity = similarities.get(item["memory_id"], -1)
            semantic = similarity >= self.semantic_threshold
            if lexical < 0.25 and not semantic:
                continue
            score = lexical + (0.65 + (similarity - self.semantic_threshold) if semantic else 0)
            scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["memory_id"]))
        result["items"] = [item for _, item in scored[:8]]
        profile = [item for item in allowed if item["kind"] == "stable_fact"
                   and item.get("semantic_key", "").removeprefix("fact:") in _PROFILE_KEYS]
        profile.sort(key=lambda item: (-self._lexical(query, item), -float(item.get("importance", 0)), item["memory_id"]))
        chars = 0
        for item in profile:
            size = len(_text(item))
            if len(result["profile"]) < 4 and chars + size <= 1200:
                result["profile"].append(item)
                chars += size
                if self._lexical(query, item) >= 0.25:
                    meta["profile_match_ids"].append(item["memory_id"])
        result["status"] = "matched" if result["items"] or result["profile"] else "no_match"
        return result
