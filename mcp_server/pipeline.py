"""Core deal-finding pipeline, shared by the MCP server and the web API.

Keeping this framework-agnostic means the exact same logic powers both the
Claude agent (via the MCP tools) and the web front-end (via FastAPI).
"""
from __future__ import annotations

import os
from typing import Iterable, Optional

from .cards import load_cards
from .coupons import find_coupons
from .matching import best_per_platform, match_report
from .models import ProductOffer
from .scrapers import SCRAPERS
from .scrapers.sample import sample_offers
from .valuation import best_across_platforms, evaluate_offer

# In-memory cache of the most recent scrape per query.
_CACHE: dict[str, list[ProductOffer]] = {}


def scrape_all(query: str, *, use_cache: bool = True) -> list[ProductOffer]:
    key = query.strip().lower()
    if use_cache and key in _CACHE:
        return _CACHE[key]

    offers: list[ProductOffer] = []
    for scraper in SCRAPERS.values():
        try:
            offers.extend(scraper.search(query))
        except Exception:  # scrapers should not raise, but never trust the web
            continue

    if not offers and os.getenv("DEAL_HUNTER_ALLOW_MOCK", "1") == "1":
        offers = sample_offers(query)

    _CACHE[key] = offers
    return offers


def is_live(offers: list[ProductOffer]) -> bool:
    return any(o.url and "SAMPLE" not in o.url for o in offers)


def run_pipeline(query: str, owned_card_ids: Optional[Iterable[str]] = None) -> dict:
    """Full pipeline: scrape -> match -> coupons -> card eval -> winner.

    If ``owned_card_ids`` is provided, only those cards are considered (models the
    real question: "what's my best price with the cards I actually hold?").
    """
    offers = scrape_all(query)
    chosen = best_per_platform(query, offers)

    cards = load_cards()
    if owned_card_ids is not None:
        owned = set(owned_card_ids)
        if owned:
            cards = [c for c in cards if c.id in owned]

    evaluations = []
    for offer in chosen.values():
        evaluations.append(evaluate_offer(offer, find_coupons(offer), cards))

    return {
        "query": query,
        "source": "live" if is_live(offers) else "sample",
        "match": match_report(query, offers),
        "per_platform": evaluations,
        "recommended": best_across_platforms(evaluations),
    }
