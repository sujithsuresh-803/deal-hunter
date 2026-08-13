"""Deterministic sample offers, used only when live scraping is blocked and
DEAL_HUNTER_ALLOW_MOCK=1. Prices are illustrative, not real.

This keeps the whole agent pipeline demoable end-to-end even when Amazon/Flipkart
CAPTCHA-wall the scraper. Swap this out once you have a reliable live source.
"""
from __future__ import annotations

from ..models import ProductOffer


def sample_offers(query: str) -> list[ProductOffer]:
    q = query.strip() or "product"
    title = q.title()
    return [
        ProductOffer(
            platform="amazon",
            title=f"{title} (Amazon listing)",
            price=68990.0,
            url="https://www.amazon.in/dp/SAMPLE",
            rating=4.3,
            reviews=2140,
            raw_offers=[
                "10% instant discount up to ₹1,500 on HDFC Bank Credit Cards",
                "No Cost EMI available",
            ],
        ),
        ProductOffer(
            platform="flipkart",
            title=f"{title} (Flipkart listing)",
            price=67499.0,
            url="https://www.flipkart.com/p/SAMPLE",
            rating=4.4,
            reviews=1876,
            raw_offers=[
                "10% off up to ₹1,750 on Axis Bank Credit Card",
                "Extra ₹1,000 off (auto-applied)",
            ],
        ),
        ProductOffer(
            platform="hp",
            title=f"{title} (HP Store)",
            price=69990.0,
            url="https://www.hp.com/in-en/shop/SAMPLE",
            rating=None,
            raw_offers=[
                "Flat ₹3,000 off with coupon HPWELCOME",
                "5% cashback on ICICI Bank Credit Cards",
            ],
        ),
    ]
