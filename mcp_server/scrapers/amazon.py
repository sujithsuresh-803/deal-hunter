"""Amazon.in search scraper (best-effort).

Amazon rotates its markup and bot-walls scrapers frequently. The selectors below
target the current search-results layout; expect to revisit them. On any failure
we return [] so the server can fall back to sample data.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Scraper
from .http import BlockedError, fetch
from ..models import ProductOffer


class AmazonScraper(Scraper):
    platform = "amazon"
    BASE = "https://www.amazon.in"

    def search(self, query: str) -> list[ProductOffer]:
        url = f"{self.BASE}/s?k={query.replace(' ', '+')}"
        try:
            html = fetch(url)
        except BlockedError:
            return []

        soup = BeautifulSoup(html, "lxml")
        offers: list[ProductOffer] = []

        for card in soup.select('div[data-component-type="s-search-result"]'):
            # Amazon rotates where the title lives. Prefer the title-recipe
            # block, then the h2's full text; take whichever is longest so we
            # get the product name, not just the brand row.
            candidates = [
                el.get_text(" ", strip=True)
                for el in card.select("h2, [data-cy='title-recipe'] h2, [data-cy='title-recipe']")
            ]
            # Drop the "You are seeing this ad" sponsored disclaimer and strip a
            # leading "Sponsored" badge that Amazon prepends to promoted cards.
            candidates = [
                re.sub(r"^(Sponsored\s+)+", "", c).strip()
                for c in candidates
                if "seeing this ad" not in c.lower()
            ]
            title = max(candidates, key=len) if candidates else ""
            if len(title) < 5:
                continue

            link_el = card.select_one("h2 a[href]") or card.select_one("a.a-link-normal[href]")
            href = link_el["href"] if link_el else ""
            product_url = href if href.startswith("http") else self.BASE + href

            price_el = card.select_one("span.a-price span.a-offscreen") or \
                card.select_one("span.a-price-whole")
            price = self.parse_price(price_el.get_text() if price_el else None)

            rating_el = card.select_one("span.a-icon-alt")
            rating = None
            if rating_el:
                rating = self.parse_price(rating_el.get_text().split(" ")[0])

            offers.append(
                ProductOffer(
                    platform=self.platform,
                    title=title,
                    price=price,
                    url=product_url,
                    rating=rating,
                    in_stock=price is not None,
                )
            )
            if len(offers) >= self.max_results():
                break

        return offers
