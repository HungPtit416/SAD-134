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

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:  # noqa: BLE001
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]


def _client() -> "OpenAI | None":
    if not settings.OPENAI_API_KEY:
        return None
    if OpenAI is None:
        return None
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _gemini_client():
    if not getattr(settings, "GEMINI_API_KEY", ""):
        return None
    if genai is None:
        return None
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def embed_texts(texts: Iterable[str]) -> EmbeddingResult:
    # Local fallback embedding (deterministic) for demos when OpenAI quota is unavailable.
    items = [t if isinstance(t, str) else str(t) for t in texts]
    if settings.EMBEDDING_PROVIDER.lower() == "local":
        return EmbeddingResult(vectors=[_local_embed(t, dim=1536) for t in items])

    provider = (settings.EMBEDDING_PROVIDER or "openai").lower()
    if provider == "openai":
        c = _client()
        if c is None:
            provider = "gemini"
        else:
            try:
                resp = c.embeddings.create(model=settings.OPENAI_EMBED_MODEL, input=items)
            except Exception as e:  # noqa: BLE001
                # Graceful fallback if quota/billing is not available.
                if RateLimitError is not None and isinstance(e, RateLimitError):
                    return EmbeddingResult(vectors=[_local_embed(t, dim=1536) for t in items])
                raise
            vectors = [d.embedding for d in resp.data]
            return EmbeddingResult(vectors=vectors)

    if provider == "gemini":
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

    raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER: {provider}")


def chat_completion(*, system: str, user: str) -> str:
    provider = (getattr(settings, "CHAT_PROVIDER", "") or "openai").lower()

    if provider == "openai" and settings.OPENAI_API_KEY and OpenAI is not None:
        c = _client()
        if c is not None:
            resp = c.chat.completions.create(
                model=settings.OPENAI_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.4,
            )
            return (resp.choices[0].message.content or "").strip()
        provider = "gemini"

    if provider == "gemini":
        gc = _gemini_client()
        if gc is None:
            raise RuntimeError("Gemini is not configured (missing GEMINI_API_KEY or google-genai package).")
        prompt = f"System:\n{system}\n\nUser:\n{user}\n"
        resp = gc.models.generate_content(
            model=getattr(settings, "GEMINI_CHAT_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config=(
                genai_types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=1024,
                    thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                )
                if genai_types is not None
                else None
            ),
        )
        return (getattr(resp, "text", "") or "").strip()

    raise RuntimeError(f"Unsupported CHAT_PROVIDER: {provider}")


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

