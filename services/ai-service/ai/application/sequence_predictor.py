from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from .interaction_gateway import list_events


BEHAVIORS_8 = [
    "view",
    "click",
    "add_to_cart",
    "purchase",
    "search",
    "browse_products",
    "browse_recommended",
    "checkout",
]

_LABEL_TO_ID = {b: i for i, b in enumerate(BEHAVIORS_8)}
_ID_TO_LABEL = {i: b for b, i in _LABEL_TO_ID.items()}


@dataclass(frozen=True)
class NextActionPrediction:
    enabled: bool
    action: str | None
    confidence: float | None
    probs: dict[str, float] | None
    note: str


@lru_cache(maxsize=1)
def _load_model():
    p = str(getattr(settings, "SEQ_MODEL_PATH", "") or "").strip()
    if not p:
        return None
    path = Path(p)
    if not path.exists():
        return None
    try:
        import tensorflow as tf
    except Exception:  # noqa: BLE001
        return None
    try:
        return tf.keras.models.load_model(path)
    except Exception:  # noqa: BLE001
        return None


def predict_next_action(user_id: str, *, seq_len: int = 6) -> NextActionPrediction:
    model = _load_model()
    if model is None:
        return NextActionPrediction(
            enabled=False,
            action=None,
            confidence=None,
            probs=None,
            note="SEQ_MODEL_PATH not configured or model not available.",
        )

    events = list_events(user_id, limit=100)
    seq: list[int] = []
    for e in reversed(events):  # oldest -> newest
        a = (e.event_type or "").strip()
        if a in _LABEL_TO_ID:
            seq.append(_LABEL_TO_ID[a])
        if len(seq) >= seq_len:
            break

    if len(seq) < seq_len:
        return NextActionPrediction(
            enabled=True,
            action=None,
            confidence=None,
            probs=None,
            note=f"Not enough actions to predict (need {seq_len}, got {len(seq)}).",
        )

    import numpy as np

    x = np.asarray([seq[-seq_len:]], dtype=np.int32)
    probs = model.predict(x, verbose=0)[0]
    best = int(np.argmax(probs))
    action = _ID_TO_LABEL.get(best)
    conf = float(probs[best]) if best < len(probs) else None

    top = sorted(
        ((str(_ID_TO_LABEL.get(i, str(i))), float(probs[i])) for i in range(min(len(probs), len(BEHAVIORS_8)))),
        key=lambda t: t[1],
        reverse=True,
    )[:5]
    return NextActionPrediction(
        enabled=True,
        action=action,
        confidence=conf,
        probs={k: v for k, v in top},
        note="ok",
    )

