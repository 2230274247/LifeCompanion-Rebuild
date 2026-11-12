"""Offline-only fastembed adapter. Call warmup() from a startup worker."""
from __future__ import annotations

import threading
from pathlib import Path


MODEL_NAME = "BAAI/bge-small-zh-v1.5"
LARGE_MODEL_NAME = "BAAI/bge-large-zh-v1.5-pinned-q8"
LARGE_MODEL_REVISION = "a48549b3259a6165364f226599cd91f39923d5d5"
LARGE_MODEL_FOLDER = "bge-large-zh-" + LARGE_MODEL_REVISION

RERANK_MODEL_NAME = "Xenova/bge-reranker-base"
RERANK_MODEL_REVISION = "280bcc27a84e0b898c251e06fddb25171bd9b101"
RERANK_MODEL_FOLDER = "bge-reranker-base-" + RERANK_MODEL_REVISION


class EmbeddingUnavailable(RuntimeError):
    pass


class LocalEmbedding:
    """Construction and query encoding never load or download a model.

    fastembed 0.7.4 passes local_files_only through TextEmbedding's **kwargs
    to both its HuggingFace and URL cache loaders. Do not retry without it.
    """

    model_name = MODEL_NAME

    def __init__(self, cache_dir, model_name=None):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.model_name = model_name or MODEL_NAME
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

                options = {}
                if self.model_name == LARGE_MODEL_NAME:
                    local_path = self.cache_dir / LARGE_MODEL_FOLDER / "context-512"
                    if not (local_path / "onnx/model_quantized.onnx").is_file():
                        self.status = "cache_missing"
                        return self.status
                    from fastembed.common.model_description import PoolingType, ModelSource
                    if not any(row["model"] == LARGE_MODEL_NAME for row in TextEmbedding.list_supported_models()):
                        TextEmbedding.add_custom_model(
                            LARGE_MODEL_NAME, pooling=PoolingType.CLS, normalization=True,
                            sources=ModelSource(hf="Xenova/bge-large-zh-v1.5"), dim=1024,
                            model_file="onnx/model_quantized.onnx", license="mit")
                    options["specific_model_path"] = str(local_path)
                elif self.model_name != MODEL_NAME:
                    self.status = "unsupported_model"
                    return self.status
                model = TextEmbedding(
                    model_name=self.model_name,
                    cache_dir=str(self.cache_dir),
                    threads=2,
                    local_files_only=True,
                    lazy_load=False,
                    **options,
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


class LocalReranker:
    """Offline-only cross-encoder for two-stage semantic recall.

    warmup() materializes the pinned quantized bge-reranker-base ONNX from the
    configured local cache; it never downloads and never blocks retrieval. When
    the model is absent or fails to load, retrieve() falls back to bi-encoder
    ordering and stays fully semantic.
    """

    model_name = RERANK_MODEL_NAME

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
            local_path = self.cache_dir / RERANK_MODEL_FOLDER
            if not (local_path / "onnx/model_quantized.onnx").is_file():
                self.status = "cache_missing"
                return self.status
            self.status = "warming"
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder
                from fastembed.common.model_description import ModelSource

                if not any(row["model"] == RERANK_MODEL_NAME
                           for row in TextCrossEncoder.list_supported_models()):
                    TextCrossEncoder.add_custom_model(
                        RERANK_MODEL_NAME,
                        sources=ModelSource(hf=RERANK_MODEL_NAME),
                        model_file="onnx/model_quantized.onnx",
                        license="mit")
                self._model = TextCrossEncoder(
                    RERANK_MODEL_NAME,
                    specific_model_path=str(local_path),
                    local_files_only=True,
                    threads=2)
                self.status = "ready"
            except ImportError:
                self.status = "dependency_missing"
            except Exception:
                self.status = "load_failed"
            return self.status
        finally:
            self._lock.release()

    def rerank(self, query, docs):
        if self.status != "ready":
            raise RuntimeError(self.status)
        if not docs:
            return []
        return list(self._model.rerank(query, docs, batch_size=8))
