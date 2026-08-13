"""Flipkart search scraper (best-effort).

Flipkart uses obfuscated, frequently-rotated class names and renders some listings
client-side. We try several selector fallbacks; for JS-heavy pages a Playwright
fetch (not wired in by default) would be more reliable.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from .base import Scraper
from .http import BlockedError, fetch
from ..models import ProductOffer


class FlipkartScraper(Scraper):
    platform = "flipkart"
    BASE = "https://www.flipkart.com"

    def search(self, query: str) -> list[ProductOffer]:
        url = f"{self.BASE}/search?q={query.replace(' ', '%20')}"
        try:
            html = fetch(url)
        except BlockedError:
            return []

        soup = BeautifulSoup(html, "lxml")
        offers: list[ProductOffer] = []

        # Flipkart lays cards out differently across categories. Anchor on any
        # link to a /p/ product page, then read title + nearest price.
        seen: set[str] = set()
        for link in soup.select('a[href*="/p/"]'):
            href = link.get("href", "")
            if not href or href in seen:
                continue

            title = link.get("title") or link.get_text(strip=True)
            if not title or len(title) < 8:
                continue

            product_url = href if href.startswith("http") else self.BASE + href

            # Price is usually a sibling/descendant element starting with ₹.
            container = link.find_parent()
            price = None
            if container:
                price_el = container.find(string=lambda s: s and "₹" in s)
                price = self.parse_price(price_el)

            seen.add(href)
            offers.append(
                ProductOffer(
                    platform=self.platform,
                    title=title,
                    price=price,
                    url=product_url,
                    in_stock=price is not None,
                )
            )
            if len(offers) >= self.max_results():
                break

        return offers
