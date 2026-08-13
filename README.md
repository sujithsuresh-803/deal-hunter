# Deal Hunter 🛒

An **MCP-based agentic AI** that finds the cheapest real cost to buy a product in
India. Given something like *"HP Victus gaming laptop"*, it:

1. **Compares prices** across Amazon.in, Flipkart, and the HP India store (live scraping).
2. **Matches** the listings to confirm they're the same product.
3. **Finds coupons** (codes + auto-applied cart discounts).
4. **Evaluates payment cards** — instant bank discounts + reward/cashback value.
5. **Recommends** the single cheapest combination: *platform + coupon + card → net price*.

The "brain" is **Claude Opus 5**, which orchestrates the tools; the tools live in a
**Model Context Protocol (MCP) server**, so any MCP client (this agent, Claude
Desktop, etc.) can drive them.

---

## Architecture

```
   Web browser                         Claude Opus 5
        │                              (agent/agent.py)
        │ HTTP                              │ MCP (stdio)
   ┌────▼─────────────┐            ┌────────▼──────────┐
   │ webapp/app.py    │            │ mcp_server/       │
   │ (FastAPI + SPA)  │            │ server.py         │
   └────┬─────────────┘            └────────┬──────────┘
        │                                   │
        └──────────────┬────────────────────┘
                       ▼
            mcp_server/pipeline.py   ← one shared core, two front doors
                       │
   ┌───────────┬───────┴───────┬─────────────┐
   ▼           ▼               ▼             ▼
 scrapers/  matching.py    coupons.py    valuation.py
 amazon     (same-product) (codes)       (best card + coupon math)
 flipkart                                cards.py ← data/cards.json
 hp
```

> 📚 **New to the concepts here?** [`docs/CONCEPTS.md`](docs/CONCEPTS.md) teaches every
> idea used — agentic AI, MCP, the Claude API, scraping, fuzzy matching, the valuation
> engine, FastAPI, the SPA front-end, async — each tied to the exact code that uses it.

**Why this shape?** The deal-finding logic lives in `pipeline.py` and is
framework-agnostic. The **web app** (FastAPI) and the **Claude agent** (MCP) are
just two front doors onto the same engine — so the demo you click and the AI that
reasons over it can never drift apart. And because the tools are exposed over MCP,
you can also drive them straight from Claude Desktop.

---

## Setup

```bash
cd deal-hunter
pip install -r requirements.txt
cp .env.example .env        # then put your ANTHROPIC_API_KEY in .env
```

Optional (more reliable scraping of JS-heavy pages):

```bash
pip install playwright && playwright install chromium
```

---

## Run

**Web app** (the showcase surface — enter a product, pick the cards you own, see the winning deal):

```bash
uvicorn webapp.app:app --reload
```

Then open http://127.0.0.1:8000. No API key needed — the web app talks to the
engine directly (the Claude agent is the separate CLI below).

**Full agent** (natural language in, recommendation out — uses Claude Opus 5):

```bash
python -m agent.agent "HP Victus gaming laptop"
```

**Just the MCP server** (for Claude Desktop or another MCP client):

```bash
python -m mcp_server.server
```

Register it with Claude Desktop by adding to its MCP config:

```json
{
  "mcpServers": {
    "deal-hunter": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/deal-hunter"
    }
  }
}
```

---

## The tools

| Tool | What it does |
|------|--------------|
| `search_products(query)` | Live-scrape all three platforms; returns raw listings. |
| `compare_prices(query)` | Match the same product across platforms + confidence score. |
| `get_coupons(query)` | Coupon codes and auto-applied discounts per platform. |
| `list_card_offers()` | The card catalogue and how each earns value. |
| `find_best_deal(query)` | One-shot: the whole pipeline → the winning combination. |

The card catalogue lives in [`data/cards.json`](data/cards.json) — edit it to add
your own cards, instant-discount rules, and reward rates.

---

## The valuation math

For each platform's listing, every card is scored by **net effective price**:

```
listed price
  − best coupon           (auto/coded)
  = after_coupon
  − instant bank discount (card, applied on the post-coupon amount)
  = amount charged to card
  − reward/cashback value (on amount charged)
  = NET EFFECTIVE PRICE   ← ranked; lowest wins
```

The globally cheapest net price across all platforms is the recommendation.

---

## Important caveats

- **Scraping is best-effort and fragile.** Amazon.in and Flipkart rotate their
  markup and run bot detection; selectors *will* need maintenance, and requests
  get CAPTCHA-walled sometimes. Each scraper fails soft (returns nothing) rather
  than crashing.
- **Sample fallback.** If *all* platforms block the scraper and
  `DEAL_HUNTER_ALLOW_MOCK=1`, the server serves illustrative sample data so the
  pipeline still runs end-to-end. Tool results are labelled `"source": "sample"`
  vs `"live"` so you always know which you got.
- **Card & coupon data is a starter set**, not exhaustive or real-time. Bank
  offers change constantly — treat `data/cards.json` as a template to maintain.
- **Respect each site's Terms of Service and `robots.txt`.** This is a personal
  research tool; don't point it at sites that forbid scraping, and don't hammer
  them (there's a small retry/backoff, but no aggressive crawling).
- **Not financial advice.** Reward valuations are simplified; verify offers on
  the platform before buying.
