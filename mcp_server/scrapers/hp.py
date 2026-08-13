"""HP India online store scraper (best-effort).

The HP India storefront (hp.com/in-en/shop) exposes a search results page.
Markup varies by category and campaign; selectors below are best-effort.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from .base import Scraper
from .http import BlockedError, fetch
from ..models import ProductOffer


class HPScraper(Scraper):
    platform = "hp"
    BASE = "https://www.hp.com"

    def search(self, query: str) -> list[ProductOffer]:
        url = f"{self.BASE}/in-en/shop/SearchDisplay?searchTerm={query.replace(' ', '+')}"
        try:
            html = fetch(url)
        except BlockedError:
            return []

        soup = BeautifulSoup(html, "lxml")
        offers: list[ProductOffer] = []

        for card in soup.select('[data-testid*="product"], .product-tile, li.product'):
            title_el = card.select_one(
                '[data-testid*="title"], .product-title, a[title]'
            )
            if not title_el:
                continue
            title = title_el.get("title") or title_el.get_text(strip=True)
            if not title:
                continue

            link_el = card.select_one("a[href]")
            href = link_el["href"] if link_el else ""
            product_url = href if href.startswith("http") else self.BASE + href

            price_el = card.find(string=lambda s: s and "₹" in s)
            price = self.parse_price(price_el)

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
