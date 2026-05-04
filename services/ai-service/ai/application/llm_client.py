"""
Google Gemini for chat and vector embeddings, with optional deterministic local embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.conf import settings

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:  # noqa: BLE001
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]


def _gemini_client():
    if not getattr(settings, "GEMINI_API_KEY", ""):
        return None
    if genai is None:
        return None
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def embed_texts(texts: Iterable[str]) -> EmbeddingResult:
    items = [t if isinstance(t, str) else str(t) for t in texts]
    provider = (getattr(settings, "EMBEDDING_PROVIDER", "") or "gemini").lower()
    if provider == "local":
        return EmbeddingResult(vectors=[_local_embed(t, dim=1536) for t in items])

    if provider != "gemini":
        raise RuntimeError(
            f"Unsupported EMBEDDING_PROVIDER: {provider!r}. Use 'gemini' or 'local'."
        )

    gc = _gemini_client()
    if gc is None or genai_types is None:
        raise RuntimeError("Gemini is not configured (missing GEMINI_API_KEY or google-genai package).")
    resp = gc.models.embed_content(
        model=getattr(settings, "GEMINI_EMBED_MODEL", "gemini-embedding-001"),
        contents=items,
        config=genai_types.EmbedContentConfig(output_dimensionality=1536),
    )
    vectors: list[list[float]] = []
    for e in (resp.embeddings or []):
        vectors.append(list(e.values))
    return EmbeddingResult(vectors=vectors)


def chat_completion(*, system: str, user: str) -> str:
    gc = _gemini_client()
    if gc is None:
        raise RuntimeError("Gemini is not configured (missing GEMINI_API_KEY or google-genai package).")
    if genai_types is None:
        raise RuntimeError("google-genai package is not available.")
    prompt = f"System:\n{system}\n\nUser:\n{user}\n"
    resp = gc.models.generate_content(
        model=getattr(settings, "GEMINI_CHAT_MODEL", "gemini-2.5-flash"),
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=1024,
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return (getattr(resp, "text", "") or "").strip()


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
