"""Shared rating helpers for recommendations and chat heuristics."""

from __future__ import annotations

import math
import re

from .product_gateway import Product


def product_rating_value(p: Product) -> float:
    try:
        return float(p.ratings) if p.ratings is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def product_rating_count(p: Product) -> int:
    try:
        return int(p.no_of_ratings) if p.no_of_ratings is not None else 0
    except (TypeError, ValueError):
        return 0


def rating_quality_score(p: Product) -> float:
    """
    Ranking score blending star rating and review volume.
    Higher is better; 0 when unrated.
    """

    r = product_rating_value(p)
    if r <= 0:
        return 0.0
    n = product_rating_count(p)
    prior_mean = 3.5
    prior_weight = 5.0
    blended = (r * n + prior_mean * prior_weight) / (n + prior_weight)
    return blended * math.log1p(max(0, n))


def query_mentions_rating(q: str) -> bool:
    s = (q or "").lower()
    return bool(
        re.search(
            r"rating|đánh giá|danh gia|review|sao|nhiều lượt|nhieu luot|lượt đánh giá|luot danh gia",
            s,
            flags=re.I,
        )
    )


def query_wants_high_rating(q: str) -> bool:
    s = (q or "").lower()
    if any(
        k in s
        for k in [
            "thấp nhất",
            "thap nhat",
            "thấp",
            "thap",
            "kém nhất",
            "kem nhat",
            "lowest",
            "worst",
            "ít sao",
            "it sao",
        ]
    ):
        return False
    return any(
        k in s
        for k in [
            "cao nhất",
            "cao nhat",
            "tốt nhất",
            "tot nhat",
            "đánh giá cao",
            "danh gia cao",
            "rating cao",
            "best rated",
            "highest",
            "nhiều sao",
            "nhieu sao",
            "đánh giá tốt",
            "danh gia tot",
        ]
    )


def query_wants_low_rating(q: str) -> bool:
    s = (q or "").lower()
    return any(
        k in s
        for k in [
            "thấp nhất",
            "thap nhat",
            "kém nhất",
            "kem nhat",
            "rating thấp",
            "rating thap",
            "đánh giá thấp",
            "danh gia thap",
            "lowest",
            "worst",
            "ít sao",
            "it sao",
        ]
    )


def format_rating_line(p: Product) -> str:
    r = product_rating_value(p)
    n = product_rating_count(p)
    cat = f" — {p.category_name}" if p.category_name else ""
    if r <= 0:
        return f"**{p.name}** (product_id: {p.id}){cat} — chưa có rating"
    count_txt = f", {n} lượt đánh giá" if n > 0 else ""
    return f"**{p.name}** (product_id: {p.id}){cat} — **{r:.1f}/5**{count_txt}"
