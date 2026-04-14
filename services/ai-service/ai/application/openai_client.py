from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.conf import settings

try:
    from openai import OpenAI
    from openai import RateLimitError
except Exception:  # noqa: BLE001
    OpenAI = None  # type: ignore[assignment]
    RateLimitError = None  # type: ignore[assignment]


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]


def _client() -> "OpenAI | None":
    if not settings.OPENAI_API_KEY:
        return None
    if OpenAI is None:
        return None
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def embed_texts(texts: Iterable[str]) -> EmbeddingResult:
    # Local fallback embedding (deterministic) for demos when OpenAI quota is unavailable.
    items = [t if isinstance(t, str) else str(t) for t in texts]
    if settings.EMBEDDING_PROVIDER.lower() == "local":
        return EmbeddingResult(vectors=[_local_embed(t, dim=1536) for t in items])

    c = _client()
    if c is None:
        raise RuntimeError("OpenAI is not configured (missing OPENAI_API_KEY or openai package).")
    try:
        resp = c.embeddings.create(model=settings.OPENAI_EMBED_MODEL, input=items)
    except Exception as e:  # noqa: BLE001
        # Graceful fallback if quota/billing is not available.
        if RateLimitError is not None and isinstance(e, RateLimitError):
            return EmbeddingResult(vectors=[_local_embed(t, dim=1536) for t in items])
        raise
    vectors = [d.embedding for d in resp.data]
    return EmbeddingResult(vectors=vectors)


def chat_completion(*, system: str, user: str) -> str:
    c = _client()
    if c is None:
        raise RuntimeError("OpenAI is not configured (missing OPENAI_API_KEY or openai package).")
    resp = c.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
    )
    return (resp.choices[0].message.content or "").strip()


def _local_embed(text: str, dim: int = 1536) -> list[float]:
    """
    A lightweight deterministic embedding for offline/demo mode.
    Not semantically strong, but enables end-to-end RAG plumbing.
    """

    import hashlib

    b = hashlib.sha256(text.encode("utf-8")).digest()
    out = [0.0] * dim
    for i in range(dim):
        out[i] = ((b[i % len(b)] / 255.0) * 2.0) - 1.0
    return out

