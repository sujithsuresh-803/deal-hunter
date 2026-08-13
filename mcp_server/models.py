"""Shared data structures passed between scrapers, valuation, and the MCP tools.

Everything is a plain dataclass with a ``to_dict`` so it serializes cleanly into
MCP tool results (which must be JSON).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ProductOffer:
    """One product as listed on one platform."""

    platform: str                 # "amazon" | "flipkart" | "hp"
    title: str
    price: Optional[float]        # ₹, None if unavailable / out of stock
    url: str
    rating: Optional[float] = None
    reviews: Optional[int] = None
    in_stock: bool = True
    # Free-text offer lines scraped from the product/listing card
    # (e.g. "10% instant discount on HDFC Bank Credit Cards").
    raw_offers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Coupon:
    """A discount code or automatic offer applicable to a platform."""

    platform: str
    code: Optional[str]           # None => auto-applied / no code needed
    description: str
    kind: str                     # "percent" | "flat"
    value: float                  # percent (e.g. 10) or flat rupees (e.g. 500)
    max_discount: Optional[float] = None   # cap for percent coupons
    min_order: Optional[float] = None
    source: str = "unknown"       # where we found it

    def discount_on(self, price: float) -> float:
        if self.min_order and price < self.min_order:
            return 0.0
        if self.kind == "percent":
            d = price * self.value / 100.0
            if self.max_discount is not None:
                d = min(d, self.max_discount)
            return round(d, 2)
        return round(min(self.value, price), 2)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CardOffer:
    """A payment card and how it earns value on a given platform."""

    name: str                     # "HDFC Millennia Credit Card"
    network: str                  # "Visa" | "Mastercard" | "RuPay" | "Amex"
    id: str = ""                  # stable slug, populated by load_cards()
    # Instant discount configured per platform: {"amazon": {...}, ...}
    # Each entry: {"percent": 10, "max_discount": 1500, "min_order": 5000}
    instant_discounts: dict = field(default_factory=dict)
    # Baseline reward rate as a fraction of spend returned in value
    # (cashback / points redeemable value). e.g. 0.05 = 5% back.
    reward_rate: float = 0.0
    reward_cap: Optional[float] = None      # cap on reward value per txn
    notes: str = ""

    def instant_discount_on(self, platform: str, price: float) -> float:
        cfg = self.instant_discounts.get(platform)
        if not cfg:
            return 0.0
        if cfg.get("min_order") and price < cfg["min_order"]:
            return 0.0
        d = price * cfg.get("percent", 0) / 100.0
        cap = cfg.get("max_discount")
        if cap is not None:
            d = min(d, cap)
        return round(d, 2)

    def reward_value_on(self, spend: float) -> float:
        d = spend * self.reward_rate
        if self.reward_cap is not None:
            d = min(d, self.reward_cap)
        return round(d, 2)

    def to_dict(self) -> dict:
        return asdict(self)
