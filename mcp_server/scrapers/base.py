"""Base scraper contract + a shared price parser.

Each platform scraper implements ``search(query) -> list[ProductOffer]``.
Scrapers must never raise on network/bot failure — they return [] and let the
server decide whether to substitute sample data.
"""
from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod

from ..models import ProductOffer


class Scraper(ABC):
    platform: str = "base"

    @abstractmethod
    def search(self, query: str) -> list[ProductOffer]:
        ...

    # --- helpers shared by concrete scrapers ---------------------------------

    @staticmethod
    def parse_price(text: str | None) -> float | None:
        """Pull a rupee amount out of messy text like '₹1,23,499'."""
        if not text:
            return None
        cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def max_results() -> int:
        return int(os.getenv("DEAL_HUNTER_MAX_RESULTS", "5"))
