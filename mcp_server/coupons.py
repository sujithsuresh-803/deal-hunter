"""Coupon discovery.

Two sources:
  1. Offer lines scraped from the product/listing card (``ProductOffer.raw_offers``),
     parsed into structured Coupon objects.
  2. A small bundled catalogue of standing coupons per platform.

Bank-card *instant discounts* embedded in offer lines are intentionally skipped
here — those are modelled through the card catalogue (see cards.py / valuation.py)
so they don't get double-counted.
"""
from __future__ import annotations

import re

from .models import Coupon, ProductOffer

# Standing / well-known coupons. Extend freely.
_CATALOGUE: list[Coupon] = [
    Coupon(
        platform="hp",
        code="HPWELCOME",
        description="Flat ₹3,000 off for new HP Store customers",
        kind="flat",
        value=3000,
        min_order=40000,
        source="catalogue",
    ),
]

_BANK_HINT = re.compile(r"\b(bank|credit card|debit card|emi)\b", re.I)


def _looks_like_card_offer(line: str) -> bool:
    return bool(_BANK_HINT.search(line))


def parse_offer_line(platform: str, line: str) -> Coupon | None:
    """Turn a free-text offer line into a Coupon, or None if it isn't one."""
    if _looks_like_card_offer(line):
        return None  # handled by the card model, not as a coupon

    code_match = re.search(r"\b(?:code|coupon)\s+([A-Z0-9]{4,})\b", line, re.I) or \
        re.search(r"\b([A-Z]{3,}[A-Z0-9]{2,})\b", line)
    code = code_match.group(1) if code_match else None

    # "10% off up to ₹1,750"
    pct = re.search(r"(\d{1,2})\s*%\s*(?:off|discount)", line, re.I)
    cap = re.search(r"up to\s*₹?\s*([\d,]+)", line, re.I)
    if pct:
        return Coupon(
            platform=platform,
            code=code,
            description=line.strip(),
            kind="percent",
            value=float(pct.group(1)),
            max_discount=float(cap.group(1).replace(",", "")) if cap else None,
            source="scraped",
        )

    # "Flat ₹3,000 off" / "Extra ₹1,000 off"
    flat = re.search(r"(?:flat|extra|₹)\s*₹?\s*([\d,]+)\s*off", line, re.I)
    if flat:
        return Coupon(
            platform=platform,
            code=code,
            description=line.strip(),
            kind="flat",
            value=float(flat.group(1).replace(",", "")),
            source="scraped",
        )
    return None


def find_coupons(offer: ProductOffer) -> list[Coupon]:
    """All coupons applicable to a given product offer."""
    found: list[Coupon] = [c for c in _CATALOGUE if c.platform == offer.platform]
    for line in offer.raw_offers:
        coupon = parse_offer_line(offer.platform, line)
        if coupon:
            found.append(coupon)
    return found
