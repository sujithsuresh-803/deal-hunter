"""Scraper registry."""
from __future__ import annotations

from .amazon import AmazonScraper
from .flipkart import FlipkartScraper
from .hp import HPScraper
from .base import Scraper

SCRAPERS: dict[str, Scraper] = {
    "amazon": AmazonScraper(),
    "flipkart": FlipkartScraper(),
    "hp": HPScraper(),
}

__all__ = ["SCRAPERS", "Scraper", "AmazonScraper", "FlipkartScraper", "HPScraper"]
