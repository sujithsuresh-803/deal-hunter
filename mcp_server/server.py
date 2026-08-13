"""Deal Hunter — MCP server.

Exposes the product-comparison toolkit over the Model Context Protocol so any
MCP-capable client (the bundled agent, Claude Desktop, etc.) can drive it.

Tools
-----
search_products(query)      Live-scrape Amazon.in / Flipkart / HP India.
compare_prices(query)       Match the same product across platforms, cheapest base.
get_coupons(query)          Discover coupons for each platform's best listing.
list_card_offers()          The payment-card catalogue and how each earns value.
find_best_deal(query)       Full pipeline: compare -> coupons -> cards -> winner.

Run:  python -m mcp_server.server        (stdio transport)
"""
from __future__ import annotations

try:  # mcp >= 2.0 renamed FastMCP -> MCPServer (same decorator/run API)
    from mcp.server import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from .cards import load_cards
from .coupons import find_coupons
from .matching import best_per_platform, match_report
from .pipeline import run_pipeline, scrape_all
from .scrapers import SCRAPERS  # noqa: F401 (kept for discoverability)

mcp = _Server("deal-hunter")


@mcp.tool()
def search_products(query: str) -> dict:
    """Search Amazon.in, Flipkart, and HP India for a product.

    Returns every listing found per platform (title, price in ₹, url, rating,
    and any raw offer lines). Falls back to illustrative sample data if all
    platforms block the scraper and mock mode is enabled.
    """
    from .pipeline import is_live

    offers = scrape_all(query)
    return {
        "query": query,
        "source": "live" if is_live(offers) else "sample",
        "count": len(offers),
        "offers": [o.to_dict() for o in offers],
    }


@mcp.tool()
def compare_prices(query: str) -> dict:
    """Match the same product across platforms and rank by base price.

    Use this to confirm the listings really are the same item before comparing
    prices. Returns a same-product confidence score and the cheapest base price.
    """
    return match_report(query, scrape_all(query))


@mcp.tool()
def get_coupons(query: str) -> dict:
    """Find coupons applicable to the best listing on each platform.

    Card-based bank offers are excluded here (they're modelled via the card
    catalogue); this returns coupon codes and automatic cart discounts only.
    """
    chosen = best_per_platform(query, scrape_all(query))
    result = {}
    for platform, offer in chosen.items():
        result[platform] = [c.to_dict() for c in find_coupons(offer)]
    return {"query": query, "coupons_by_platform": result}


@mcp.tool()
def list_card_offers() -> dict:
    """List the payment-card catalogue: instant discounts per platform + reward rates."""
    return {"cards": [c.to_dict() for c in load_cards()]}


@mcp.tool()
def find_best_deal(query: str) -> dict:
    """Full pipeline: compare platforms, apply best coupon + card, pick the winner.

    This is the one-shot tool. It scrapes, matches the product across platforms,
    finds coupons, evaluates every card, and returns the single cheapest way to
    buy — including which platform, which coupon, and which card to pay with.
    """
    return run_pipeline(query)


if __name__ == "__main__":
    mcp.run()
