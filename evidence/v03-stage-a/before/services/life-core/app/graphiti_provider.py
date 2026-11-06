from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GraphitiStatus:
    state: str
    reason: str
    package_version: str


class GraphitiUnavailable(RuntimeError):
    pass


class GraphitiProvider:
    """Fail-closed Graphiti gate; structural Neo4j retrieval remains independent."""

    def __init__(self, settings):
        configured = bool(
            getattr(settings, "embedding_provider", "")
            and getattr(settings, "embedding_api_key", "")
        )
        self.status = GraphitiStatus(
            state="BLOCKED_ADAPTER_VALIDATION" if configured else "BLOCKED_EMBEDDING",
            reason="Embedding provider and key are not configured"
            if not configured
            else "Embedding configuration requires explicit Graphiti adapter validation",
            package_version="0.31.2",
        )

    def add_episode(self, **_kwargs: Any):
        self._require_native_provider()

    def search(self, **_kwargs: Any):
        self._require_native_provider()

    def _require_native_provider(self):
        if self.status.state != "READY":
            raise GraphitiUnavailable(self.status.state)
