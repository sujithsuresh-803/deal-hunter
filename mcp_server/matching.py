"""Cross-platform product matching.

Given raw search results from several platforms, decide which listings refer to
the *same* product so prices are compared apples-to-apples. Uses normalized token
overlap plus model-number extraction (a strong signal for electronics).
"""
from __future__ import annotations

import re

from .models import ProductOffer

_STOPWORDS = {
    "the", "with", "and", "for", "gb", "inch", "laptop", "new", "latest",
    "processor", "ram", "ssd", "display", "warranty",
}


def _tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def _model_codes(title: str) -> set[str]:
    """Alphanumeric codes like 'fa0666tx' or '15-fb' that identify a SKU."""
    return set(re.findall(r"[a-z]+\d[a-z0-9-]*|\d{2,}[a-z]+", title.lower()))


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)

    ma, mb = _model_codes(a), _model_codes(b)
    model_bonus = 0.4 if (ma & mb) else 0.0
    return round(min(1.0, jaccard + model_bonus), 3)


def best_per_platform(query: str, offers: list[ProductOffer]) -> dict[str, ProductOffer]:
    """Pick the single offer per platform most likely to be what the user asked for."""
    chosen: dict[str, ProductOffer] = {}
    best_score: dict[str, float] = {}
    for o in offers:
        if o.price is None:
            continue
        score = similarity(query, o.title)
        if score > best_score.get(o.platform, -1):
            best_score[o.platform] = score
            chosen[o.platform] = o
    return chosen


def match_report(query: str, offers: list[ProductOffer]) -> dict:
    """Build a comparison across platforms plus a same-product confidence."""
    chosen = best_per_platform(query, offers)
    picks = list(chosen.values())

    # Pairwise confidence that the chosen listings are the same product.
    pair_scores = [
        similarity(a.title, b.title)
        for i, a in enumerate(picks)
        for b in picks[i + 1:]
    ]
    confidence = round(sum(pair_scores) / len(pair_scores), 3) if pair_scores else 1.0

    comparison = sorted(
        (o.to_dict() for o in picks),
        key=lambda d: (d["price"] is None, d["price"]),
    )
    cheapest = comparison[0] if comparison else None

    return {
        "query": query,
        "same_product_confidence": confidence,
        "cheapest_base_price": cheapest,
        "comparison": comparison,
    }
