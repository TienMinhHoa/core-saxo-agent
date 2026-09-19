"""Embedding providers. Embeddings support retrieval only, never rendering."""
from __future__ import annotations

import os
import threading
from typing import Any, Protocol

from .errors import MusicRagError


class EmbeddingUnavailable(MusicRagError):
    code = "semantic_unavailable"


class EmbeddingProvider(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _exception_detail(exc: BaseException, secret: str) -> str:
    """Keep the vendor error useful without exposing the API key."""
    parts: list[str] = []
    current: BaseException | None = exc
    for _ in range(3):
        if current is None:
            break
        message = str(current).replace(secret, "<redacted>").replace(chr(10), " ")
        parts.append(f"{type(current).__name__}: {message}")
        current = current.__cause__ or current.__context__
    return " <- ".join(parts)[:500]


class OpenAIEmbeddingProvider:
    """Server-side OpenAI embeddings provider; API key never enters the UI."""

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise EmbeddingUnavailable("OPENAI_API_KEY_not_configured")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - deployment configuration
            raise EmbeddingUnavailable("openai_sdk_not_installed") from exc
        self._openai_class = OpenAI
        self.model = model or os.environ.get("MUSIC_RAG_EMBEDDING_MODEL", "text-embedding-3-small")
        self._client = OpenAI(api_key=key)
        self._api_key = key
        self._thread_local = threading.local()
        self._thread_local.client = self._client
        self._usage_lock = threading.Lock()
        self.last_usage: dict[str, int] = {"prompt_tokens": 0, "total_tokens": 0}
        self.total_usage: dict[str, int] = {"prompt_tokens": 0, "total_tokens": 0, "requests": 0}
        self.last_error: str | None = None

    def _client_for_thread(self) -> Any:
        client = getattr(self._thread_local, "client", None)
        if client is None:
            # Keep one HTTP client per worker.  This avoids sharing mutable
            # transport state when the Chroma indexer embeds batches in
            # parallel, while retaining connection pooling per worker.
            client = self._openai_class(api_key=self._api_key)
            self._thread_local.client = client
        return client

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client_for_thread().embeddings.create(model=self.model, input=texts)
        except Exception as exc:  # do not leak vendor errors or credentials to public UI
            detail = _exception_detail(exc, self._api_key)
            self.last_error = detail[:500]
            raise EmbeddingUnavailable(f"embedding_request_failed: {self.last_error}") from exc
        usage: Any = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", prompt_tokens) or prompt_tokens)
        with self._usage_lock:
            self.last_usage = {"prompt_tokens": prompt_tokens, "total_tokens": total_tokens}
            self.total_usage["prompt_tokens"] += prompt_tokens
            self.total_usage["total_tokens"] += total_tokens
            self.total_usage["requests"] += 1
        return [list(record.embedding) for record in response.data]
