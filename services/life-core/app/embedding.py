"""Offline-only fastembed adapter. Call warmup() from a startup worker."""
from __future__ import annotations

import threading
from pathlib import Path


MODEL_NAME = "BAAI/bge-small-zh-v1.5"


class EmbeddingUnavailable(RuntimeError):
    pass


class LocalEmbedding:
    """Construction and query encoding never load or download a model.

    fastembed 0.7.4 passes local_files_only through TextEmbedding's **kwargs
    to both its HuggingFace and URL cache loaders. Do not retry without it.
    """

    model_name = MODEL_NAME

    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.status = "not_warmed"
        self._model = None
        self._lock = threading.Lock()

    def warmup(self):
        if not self._lock.acquire(blocking=False):
            return self.status
        try:
            if self._model is not None:
                return "ready"
            if self.cache_dir is None or not self.cache_dir.is_dir():
                self.status = "cache_missing"
                return self.status
            self.status = "warming"
            try:
                from fastembed import TextEmbedding

                model = TextEmbedding(
                    model_name=self.model_name,
                    cache_dir=str(self.cache_dir),
                    threads=2,
                    local_files_only=True,
                    lazy_load=False,
                )
                # Materialize one non-user probe while still in the startup worker.
                list(model.embed(["本地模型预热"], batch_size=1))
                self._model = model
                self.status = "ready"
            except ImportError:
                self.status = "dependency_missing"
            except Exception:
                # Missing/corrupt/incompatible local files must never cause a download.
                self.status = "load_failed"
            return self.status
        finally:
            self._lock.release()

    def _encode(self, texts, *, query=False):
        if self.status != "ready":
            raise EmbeddingUnavailable(self.status)
        if not self._lock.acquire(blocking=False):
            raise EmbeddingUnavailable("busy")
        try:
            encoder = self._model.query_embed if query else self._model.embed
            return list(encoder(texts))
        finally:
            self._lock.release()

    def embed(self, texts):
        return self._encode(texts)

    def query_embed(self, texts):
        return self._encode(texts, query=True)
