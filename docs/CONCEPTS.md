# Deal Hunter — Concepts Explained

A guided tour of every idea used to build this project. Each section explains the
concept in general, then shows **exactly where and why** it appears in the code, with
the gotchas that actually bit us. Read it top-to-bottom to understand the whole
system, or jump to a section.

> Mental model for the whole app: **one deterministic engine, two front doors.**
> The engine finds the cheapest true price. One door is a web app (for humans), the
> other is an MCP server driven by Claude (for an AI agent). Keep that picture in
> mind and everything below slots into place.

## Contents

1. [The big picture: architecture & separation of concerns](#1-architecture--separation-of-concerns)
2. [Agentic AI & the agent loop](#2-agentic-ai--the-agent-loop)
3. [MCP — the Model Context Protocol](#3-mcp--the-model-context-protocol)
4. [The Claude API: models, tool runner, thinking, effort](#4-the-claude-api)
5. [Tool design](#5-tool-design)
6. [Web scraping](#6-web-scraping)
7. [Fuzzy matching (are these the same product?)](#7-fuzzy-matching)
8. [Domain modelling with dataclasses](#8-domain-modelling-with-dataclasses)
9. [The valuation engine (the "business logic")](#9-the-valuation-engine)
10. [The web API (FastAPI)](#10-the-web-api-fastapi)
11. [The front-end (a no-build SPA)](#11-the-front-end)
12. [Async & concurrency](#12-async--concurrency)
13. [Configuration, env vars & feature flags](#13-configuration-env-vars--feature-flags)
14. [Python patterns used throughout](#14-python-patterns-used-throughout)
15. [Glossary](#15-glossary)

---

## 1. Architecture & separation of concerns

**Concept.** *Separation of concerns* means each part of the system has one job and
knows as little as possible about the others. The payoff is that you can change one
part (say, swap the scraper) without touching the rest, and you can reuse the core
from multiple places.

The single most important architectural decision here is **"one core, two front
doors."** The deal-finding logic doesn't live in the web app *or* the AI agent — it
lives in its own module, and both front ends call it.

```
   Web browser                         Claude Opus 5
        │ HTTP                              │ MCP (stdio)
   ┌────▼─────────────┐            ┌────────▼──────────┐
   │ webapp/app.py    │            │ mcp_server/server │
   └────┬─────────────┘            └────────┬──────────┘
        └──────────────┬────────────────────┘
                       ▼
            mcp_server/pipeline.py     ← the shared core
                       │
     scrapers ── matching ── coupons ── valuation ── cards
```

**In our code.** [`mcp_server/pipeline.py`](../mcp_server/pipeline.py) exposes
`run_pipeline(query, owned_card_ids)`. It imports the scrapers, matcher, coupon
finder, card catalogue, and valuation engine and wires them together — but it knows
*nothing* about HTTP or MCP. Then:

- [`webapp/app.py`](../webapp/app.py) calls `run_pipeline(...)` from a FastAPI route.
- [`mcp_server/server.py`](../mcp_server/server.py) calls the same `run_pipeline(...)`
  from an MCP tool.

Because both go through the same function, the demo you click and the AI that reasons
over it **can never disagree**. That's not an accident — it's the reason the logic was
pulled out of both front ends into `pipeline.py`.

**Dependency direction.** Notice the arrows only point *inward*: front ends depend on
the core, never the reverse. `pipeline.py` doesn't import `app.py` or `server.py`.
Keeping dependencies pointing toward stable, generic code (and away from
framework-specific code) is a core principle — often called *dependency inversion* or
just "depend on the thing that changes least."

---

## 2. Agentic AI & the agent loop

**Concept.** A plain LLM call is *one* request → *one* answer. An **agent** is an LLM
placed in a **loop** with **tools**: the model decides which tool to call, you run it,
you feed the result back, and the model decides what to do next — repeating until it's
done. The model is doing the *planning and orchestration*; your code just executes the
steps it asks for.

The loop looks like this:

```
user request
   ↓
┌─────────────────────────────────────────────┐
│ model reads context, decides:               │
│   "call find_best_deal('HP Victus')"        │
│         ↓                                    │
│   your code runs the tool, returns JSON      │
│         ↓                                    │
│   model reads the result, decides:           │
│     tool again?  or  final answer?           │  ← loops
└─────────────────────────────────────────────┘
   ↓ (no more tools)
final answer to the user
```

**Why agentic here?** The task is genuinely multi-step and hard to fully script: which
platforms, whether the listings match, which coupons apply, which card wins. The model
can adapt — e.g. if the same-product confidence is low it can say so, or call a
granular tool to dig deeper — rather than following a fixed script.

**Deterministic vs agentic (an important nuance).** The **web app** does *not* use the
LLM. It calls `run_pipeline` directly and returns a fixed result. That's deliberate:
for a click-through demo you want it fast, free, and identical every time. The
**agent** (CLI) is where the LLM adds value — natural-language input, judgement, and a
readable explanation. Knowing *when not to use an LLM* is itself a design skill.

**In our code.** [`agent/agent.py`](../agent/agent.py) runs the loop, but we don't
hand-write the `while` loop — the Anthropic SDK's **tool runner** does it for us:

```python
runner = client.beta.messages.tool_runner(
    model=MODEL,
    system=SYSTEM,
    tools=[async_mcp_tool(t, mcp_client) for t in tools],
    messages=[{"role": "user", "content": user_query}],
)
async for message in runner:      # each iteration = one turn of the loop
    ...
```

The tool runner handles: call the API → detect a tool request → execute the tool →
feed the result back → repeat until the model stops calling tools. We just iterate the
results and print them.

---

## 3. MCP — the Model Context Protocol

**Concept.** MCP is an open standard for connecting AI models to tools and data. Think
of it as **"USB for AI tools"**: instead of hard-wiring each tool into each app, a tool
provider exposes an **MCP server**, and any **MCP client** (Claude Desktop, our agent,
etc.) can plug in and use those tools. One tool definition, many consumers.

Key pieces:

- **Server** — exposes *tools* (callable functions), *resources* (readable data), and
  *prompts*. Ours exposes 5 tools.
- **Client** — connects to a server, lists what it offers, and calls tools.
- **Transport** — how bytes move between them. We use **stdio**: the client launches
  the server as a subprocess and talks over its standard input/output. (The other
  common transport is HTTP/SSE for remote servers.)
- **Protocol** — JSON-RPC messages under the hood (`initialize`, `list_tools`,
  `call_tool`, …). The SDK hides this; you rarely see the raw messages.

**Why we used it.** It *decouples the tools from the model*. The exact same
`mcp_server` can be driven by our Python agent **or** dropped into Claude Desktop with
a few lines of config — no code changes. That's the whole point of a protocol.

**In our code — the server side.**
[`mcp_server/server.py`](../mcp_server/server.py) defines tools with a decorator and
runs over stdio:

```python
mcp = _Server("deal-hunter")

@mcp.tool()
def find_best_deal(query: str) -> dict:
    """Full pipeline: compare platforms, apply best coupon + card, pick the winner."""
    return run_pipeline(query)

if __name__ == "__main__":
    mcp.run()          # stdio transport by default
```

The tool's **docstring becomes its description** that the model reads to decide when to
call it — so docstrings here are functional, not decoration (see §5).

**In our code — the client side.**
[`agent/agent.py`](../agent/agent.py) launches the server as a subprocess and connects:

```python
server = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"])
async with stdio_client(server) as (read, write):
    async with ClientSession(read, write) as mcp_client:
        await mcp_client.initialize()
        tools = (await mcp_client.list_tools()).tools
        # convert MCP tools → Anthropic tools so Claude can call them:
        anthropic_tools = [async_mcp_tool(t, mcp_client) for t in tools]
```

`async_mcp_tool` (from `anthropic.lib.tools.mcp`) is the bridge: it wraps each MCP tool
so that when Claude decides to call it, the SDK routes the call through the MCP session
and returns the result. That single helper is what lets the two standards (Anthropic
tool use + MCP) talk to each other.

**Gotcha we hit — library version drift.** MCP is young and moving fast. We wrote the
server against `mcp.server.fastmcp.FastMCP`, but the installed `mcp 2.0` had **renamed**
it to `mcp.server.MCPServer` (same decorator/`run()` API). We made the import
version-tolerant:

```python
try:                                    # mcp >= 2.0
    from mcp.server import MCPServer as _Server
except ImportError:                     # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
```

Lesson: on fast-moving ecosystems, guard imports and pin versions in `requirements.txt`.

---

## 4. The Claude API

The concepts below are how you actually *drive* the model. All of it lives in
[`agent/agent.py`](../agent/agent.py).

**Model choice.** `MODEL = "claude-opus-5"`. Opus is the strongest tier for multi-step
tool use and reasoning — exactly what an orchestration agent needs. Model IDs are exact
strings; you don't append dates to the alias.

**System prompt.** The `system` string sets the agent's role, its working rules, and
its output format *once*, separately from the user's turn. Ours tells it: use
`find_best_deal` for simple asks, use granular tools when reasoning is wanted, always
check match confidence, and say plainly when data is `sample` vs `live`. A good system
prompt is the cheapest, highest-leverage way to shape behaviour.

**Tool runner.** `client.beta.messages.tool_runner(...)` runs the agent loop for you
(see §2). The alternative is a manual `while stop_reason == "tool_use"` loop; the runner
is the recommended default because it handles the plumbing.

**Adaptive thinking.** On Opus 5, "thinking" (the model reasoning before answering) is
on by default. You don't hand it a fixed token budget; it decides how much to think per
request. We don't set it explicitly — the default is what we want.

**Effort.** `output_config={"effort": "high"}` tunes how much the model deliberates and
how many tool calls it's willing to make. `high` suits agentic, tool-heavy work;
lower effort means terser, cheaper, faster. It's the main quality/cost dial.

**Refusal handling.** Safety classifiers can decline a request (a normal `200`
response with `stop_reason == "refusal"`, *not* an exception). We check for it before
reading content:

```python
if message.stop_reason == "refusal":
    print("[The model declined this request.]")
    return
```

Robust LLM code always checks `stop_reason` before assuming there's an answer.

---

## 5. Tool design

**Concept.** A tool the model can call is defined by a **name**, a **description**, and
an **input schema** (the parameters + types). The model reads *only these* to decide
whether and how to call it — so a tool definition is a **contract and a man page**, not
an implementation detail. Vague descriptions are the #1 cause of an agent misusing
tools.

**Granular vs one-shot tools.** We expose both:

- `search_products`, `compare_prices`, `get_coupons`, `list_card_offers` — *granular*
  steps the model can compose when it wants to reason explicitly.
- `find_best_deal` — a *one-shot* tool that runs the whole pipeline.

Offering both lets the model pick its altitude: fire one tool for a simple request, or
walk the steps when the user wants the reasoning shown. This is a deliberate tradeoff —
more tools = more flexibility but more ways to choose wrong.

**Schemas for free.** With MCP + FastMCP-style servers, the input schema is generated
from the Python function signature and type hints. `def find_best_deal(query: str)`
becomes a schema requiring a string `query`. That's why type hints matter here — they're
not just documentation, they define the tool's contract.

**Descriptions carry the weight.** In [`server.py`](../mcp_server/server.py) every tool
has a docstring written *for the model*: what it does, when to use it, and caveats
(e.g. "Card-based bank offers are excluded here — they're modelled via the card
catalogue"). That last line prevents the model from double-counting card offers as
coupons.

**Statefulness / caching.** Scraping is slow, so [`pipeline.py`](../mcp_server/pipeline.py)
caches the most recent scrape per query in a dict (`_CACHE`). When the model calls
`compare_prices` right after `search_products` for the same query, the second call
reuses the cached listings instead of re-scraping. This is a classic **memoization**
pattern: trade a little memory for a lot of latency.

---

## 6. Web scraping

**Concept.** *Scraping* = programmatically fetching web pages and extracting structured
data from their HTML. Two steps: **fetch** (HTTP) and **parse** (HTML → fields). Both
are harder than they look, because sites don't *want* to be scraped.

### Fetching — [`scrapers/http.py`](../mcp_server/scrapers/http.py)

- **Realistic headers.** Servers inspect the `User-Agent` and other headers to spot
  bots. We send a real browser UA (rotating among a few) plus `Accept-Language: en-IN`
  etc., so requests look like a normal Chrome visit.
- **Retries with backoff.** Transient failures (timeouts, brief 503s) are common. We
  retry a couple of times, sleeping a bit longer each attempt (`1.5 * (attempt+1)` plus
  jitter). *Exponential-ish backoff with jitter* avoids hammering a struggling server
  and avoids many clients retrying in lockstep.
- **Bot-wall detection.** Even with good headers you get CAPTCHA'd. We detect it — a
  `403/429/503`, or the word "captcha" in the body — and raise a typed `BlockedError`
  so callers can react instead of parsing a garbage page.

```python
if "captcha" in body[:5000].lower():
    raise BlockedError(f"{url} -> CAPTCHA wall")
```

### Parsing — the platform scrapers

We use **BeautifulSoup** with **CSS selectors** to pull fields out of the HTML. A CSS
selector like `div[data-component-type="s-search-result"]` means "every div whose
`data-component-type` attribute equals that value" — i.e. each product card. Then within
a card we select the title, price, link, rating.

```python
for card in soup.select('div[data-component-type="s-search-result"]'):
    title = ...        # from an <h2>
    price = self.parse_price(price_el.get_text())   # "₹68,990" -> 68990.0
```

`parse_price` (in [`scrapers/base.py`](../mcp_server/scrapers/base.py)) strips
everything that isn't a digit or dot — turning messy `"₹1,23,499"` into a clean float.

### The three hard truths of scraping

1. **Selectors rot.** Sites change markup constantly. We hit this live: Amazon had moved
   the product title out of `h2 a span`, so titles came back as just the brand ("HP").
   We fixed it by taking the *longest* candidate text and stripping the "Sponsored"
   badge and ad disclaimer. Expect to maintain selectors forever.
2. **Fail soft, never crash.** Every scraper returns `[]` on any failure rather than
   raising. `pipeline.scrape_all` wraps each in `try/except` too. One blocked platform
   must never take down the whole request.
3. **Legality & ethics.** Scraping can violate a site's Terms of Service and
   `robots.txt`. For a personal research tool with light traffic that's one thing; for a
   public business you'd move to **official affiliate APIs** (Amazon Associates,
   Flipkart Affiliate). We document this clearly in the README.

### The mock-fallback pattern — [`scrapers/sample.py`](../mcp_server/scrapers/sample.py)

Because live scraping is unreliable, if *all* platforms block us (and mock mode is on)
we serve deterministic **sample data** so the whole pipeline still runs. Every result is
labelled `"source": "live"` vs `"sample"` so nobody is misled. This "degrade gracefully
to seeded data" pattern is what keeps a demo from dying on stage.

---

## 7. Fuzzy matching

**Concept.** *Fuzzy matching* decides whether two differently-worded strings refer to
the same thing. We need it because a price comparison is meaningless unless the
listings are the **same product** — Amazon's "HP Smartchoice Victus, Ryzen 7 7445HS…"
and Flipkart's "HP Victus AMD Ryzen 7 Hexa Core 7445HS…" must be recognised as one item.

Our approach ([`matching.py`](../mcp_server/matching.py)) combines two signals:

**1. Token overlap (Jaccard similarity).** Break each title into a set of meaningful
words (lowercased, stripped of *stopwords* like "the", "laptop", "gb"), then measure
overlap:

```
Jaccard = |A ∩ B| / |A ∪ B|      # shared words ÷ total distinct words
```

1.0 means identical word-sets, 0.0 means no shared words. Set operations (`&`, `|`) do
the heavy lifting in one line.

**2. Model-code bonus.** For electronics, a SKU code like `15-fb3122ax` or `fa0666tx`
is a *strong* identity signal — far more reliable than marketing words. We extract those
with a regex and add a `+0.4` bonus when they match:

```python
model_bonus = 0.4 if (codes_a & codes_b) else 0.0
score = min(1.0, jaccard + model_bonus)
```

**Confidence score.** `match_report` picks the best listing per platform, then averages
the pairwise similarity of the winners into a `same_product_confidence` (0–1). The UI
shows it as a percentage and the agent is told to flag low confidence. Being honest
about uncertainty — rather than pretending every match is perfect — is good product
design.

> This is deliberately simple (no ML). It's fast, explainable, and good enough. A
> production version might add embeddings or a trained matcher — but you start simple and
> only add complexity when the simple version demonstrably fails.

---

## 8. Domain modelling with dataclasses

**Concept.** *Domain modelling* means representing the real-world things your app deals
with as clear types. Here the "domain" is deals: a **product offer**, a **coupon**, a
**payment card**. Modelling them as explicit classes (instead of loose dicts) makes the
code self-documenting and lets each type carry its own behaviour.

**Dataclasses** ([`models.py`](../mcp_server/models.py)) are Python's low-boilerplate way
to do this. `@dataclass` auto-generates `__init__`, `__repr__`, etc. from typed fields:

```python
@dataclass
class Coupon:
    platform: str
    code: str | None
    kind: str          # "percent" | "flat"
    value: float
    max_discount: float | None = None
```

**Data + behaviour together.** Crucially, the models carry the logic that belongs to
them. A `Coupon` knows how to compute its own discount; a `CardOffer` knows its instant
discount and reward value:

```python
class Coupon:
    def discount_on(self, price: float) -> float:
        if self.kind == "percent":
            d = price * self.value / 100
            return min(d, self.max_discount) if self.max_discount else d
        return min(self.value, price)
```

This keeps the rules for "how much is a coupon worth" *inside the Coupon*, not scattered
across the valuation code. When a rule changes, there's one obvious place to change it.

**Serialization.** Each model has `to_dict()` (via `dataclasses.asdict`) because MCP tool
results and JSON API responses must be plain JSON — objects don't cross those boundaries,
dicts do.

---

## 9. The valuation engine

This is the **business logic** — the part that's genuinely novel and worth showing off.
It lives in [`valuation.py`](../mcp_server/valuation.py).

**Concept.** In India, the *listed price* is rarely what you pay. Stack on top:

- a **coupon** (a code or auto-applied cart discount),
- an **instant bank discount** (e.g. "10% off with HDFC card, up to ₹1,500"),
- **reward value** (cashback / points you get back).

The product's true cost — the **net effective price** — is what's left after all three.
Nobody compares this well across platforms *and* cards, which is the app's whole reason
to exist.

**The stacking model (order matters!).** Discounts don't all apply to the same base.
We model the realistic order:

```
listed price
  − coupon              (best single coupon)
  = after_coupon
  − instant discount    (card %, applied on the POST-coupon amount)
  = amount_charged      (what actually hits your card)
  − reward value        (cashback/points on amount_charged)
  = NET EFFECTIVE PRICE
```

Why this order? The bank's instant discount is computed on the cart total *after*
coupons, and rewards accrue on what you actually *pay* (post-discount). Getting the
order wrong would overstate savings. Encoding domain rules like this correctly is the
hard, valuable part.

**The optimization.** For each platform's listing, `evaluate_offer` runs every card
through the stack and **ranks by net price** (lowest wins). A baseline "no card" option
is always included so the card benefit is visible. Then `best_across_platforms` takes
each platform's winner and picks the global cheapest:

```python
options.sort(key=lambda o: o["net_effective"])   # cheapest first
best = options[0]
```

This is a small **optimization / search problem**: over the space of (platform × coupon
× card), find the combination minimizing net price. It's brute-force (the space is tiny),
which is exactly right — don't reach for anything cleverer than the problem needs.

**Personalization.** `run_pipeline(query, owned_card_ids=...)` filters the card set to
the cards *you actually hold*. "Best price with my wallet" is a more honest and more
useful answer than "best price with a card you'd have to go get." That filter is the
product's differentiator, and it's one line.

---

## 10. The web API (FastAPI)

**Concept.** A **web API** exposes your logic over HTTP so a browser (or any client)
can call it. **FastAPI** is a Python framework that turns typed functions into HTTP
endpoints, with automatic request parsing and JSON responses.

**In our code** ([`webapp/app.py`](../webapp/app.py)):

```python
@app.get("/api/deal")
def deal(query: str = Query(..., min_length=2), cards: str | None = Query(None)) -> dict:
    owned = cards.split(",") if cards else None
    return run_pipeline(query, owned_card_ids=owned)
```

Concepts packed into those few lines:

- **Routing.** `@app.get("/api/deal")` maps an HTTP GET on that path to this function.
- **Query parameters & validation.** `Query(..., min_length=2)` declares `?query=` is
  required and must be ≥2 chars; FastAPI validates and returns a 422 automatically if
  not. Declarative validation beats hand-written `if` checks.
- **Automatic JSON.** Return a dict; FastAPI serializes it to a JSON response.
- **Sync `def` vs `async def` — a real decision.** Our scraping is *blocking* I/O (the
  `httpx.Client` calls block the thread). We wrote the endpoint as a plain `def`, which
  makes FastAPI run it in a **threadpool** so one slow scrape doesn't freeze the whole
  server. If we'd written `async def` and then called blocking code, we'd stall the event
  loop — a classic async footgun. (See §12.)
- **Serving the front-end.** `FileResponse` returns the HTML page at `/`, and
  `StaticFiles` mounts the `static/` folder. Backend and front-end ship from one server.

**Separation, again.** The API is *thin* — it parses the request, calls `run_pipeline`,
returns the result. All the real logic is in the engine. Thin controllers over a rich
core is a hallmark of maintainable web apps.

---

## 11. The front-end

**Concept.** A **single-page app (SPA)** is a web page that fetches data with JavaScript
and updates the DOM in place, instead of reloading the page. Ours
([`webapp/static/index.html`](../webapp/static/index.html)) is deliberately a **single
self-contained file** with inline CSS + JS — *no build step, no npm, no framework*. For a
portfolio demo that must run instantly and deploy trivially, that reliability is worth
more than a fancy stack.

Concepts in play:

- **The `fetch` API + `async/await`.** JavaScript calls our backend and awaits JSON:
  ```js
  const res = await fetch('/api/deal?' + params.toString());
  const data = await res.json();
  ```
- **`URLSearchParams`.** Safely builds the `?query=...&cards=...` query string
  (handles encoding for you).
- **DOM construction.** A tiny `el(tag, class, html)` helper builds elements; we append
  them to render the winner card, math strip, and comparison table.
- **Client-side state.** The selected cards live in a JavaScript `Set` (`selected`).
  Clicking a chip toggles membership; on submit we serialize the set into the request.
  A `Set` is the right structure — membership toggling, no duplicates.
- **Locale-aware formatting.** `Intl.NumberFormat('en-IN', {style:'currency',
  currency:'INR'})` formats numbers the Indian way (₹71,448 with correct grouping) with
  zero manual string work. Always use the platform's i18n APIs instead of rolling your
  own.
- **UX states.** The UI explicitly renders **loading** (spinner + message), **error**,
  and **empty** ("no priced listings") states — not just the happy path. Handling all
  states is what separates a demo that feels finished from one that feels broken.
- **Theme-aware, responsive CSS.** *CSS custom properties* (`--bg`, `--accent`, …) are
  defined once, then overridden inside `@media (prefers-color-scheme: dark)` so the page
  follows the OS light/dark setting automatically. Flexbox + relative units make it work
  on phone and desktop. Design tokens as variables = change the palette in one place.

---

## 12. Async & concurrency

**Concept.** *Concurrency* is doing multiple things without blocking. Python's
`asyncio` uses an **event loop**: `async` functions can `await` slow operations
(network, subprocess) and yield control so other work proceeds, all on one thread.

**Where it shows up.** The **agent** is fully async because MCP-over-stdio and the
Anthropic streaming API are async:

```python
async with stdio_client(server) as (read, write):        # async context manager
    async with ClientSession(read, write) as mcp_client:
        await mcp_client.initialize()                    # await = "pause here, resume when ready"
        async for message in runner:                     # async iteration over the agent loop
            ...
```

- **`async with`** — an *async context manager*. It guarantees the subprocess and
  session are set up on entry and cleanly torn down on exit, even across `await` points.
  This is how resources get released reliably in async code.
- **`await`** — "this is slow; let other work run until the result is ready."
- **`async for`** — iterate results that arrive over time (each turn of the agent loop).

**The sync/async boundary (the subtle bit).** The *engine* is plain synchronous code
(scraping with a blocking `httpx.Client`). We deliberately did **not** make it async. In
the web app we bridge the two worlds by writing the endpoint as a sync `def`, so FastAPI
runs the blocking work in a threadpool (§10). Mixing blocking calls into an async
function without that bridge is the most common async bug — it silently freezes the whole
event loop. Knowing where the boundary is matters more than making everything async.

---

## 13. Configuration, env vars & feature flags

**Concept.** Keep configuration and secrets *out of the code*. **Environment variables**
supply per-machine settings; a `.env` file holds them locally and is git-ignored.

**In our code.** `python-dotenv`'s `load_dotenv()` reads `.env` into the environment at
startup. [`.env.example`](../.env.example) documents every knob:

- `ANTHROPIC_API_KEY` — a **secret**. Never hard-code or commit it.
- `DEAL_HUNTER_MODEL`, `DEAL_HUNTER_TIMEOUT`, `DEAL_HUNTER_MAX_RESULTS` — tunables.
- `DEAL_HUNTER_ALLOW_MOCK` — a **feature flag**. When live scraping fails and this is
  `1`, the app serves sample data; set it to `0` to force live-only. Feature flags let
  you change behaviour at runtime without touching code.

Reading them safely, with defaults:

```python
MODEL = os.getenv("DEAL_HUNTER_MODEL", "claude-opus-5")   # default if unset
timeout = float(os.getenv("DEAL_HUNTER_TIMEOUT", "20"))
```

Committing `.env.example` (not `.env`) is the standard pattern: it documents what's
needed without leaking any real values.

---

## 14. Python patterns used throughout

Smaller language-level concepts that recur across the codebase:

- **Type hints** (`def search(self, query: str) -> list[ProductOffer]:`). Documentation
  the tools can read, the schema generator can use, and your editor can check.
- **`from __future__ import annotations`** at the top of every module. Makes all type
  hints lazy strings, so you can reference types without import-order headaches and use
  modern syntax (`str | None`) on any supported version.
- **Abstract Base Class (ABC).** [`Scraper`](../mcp_server/scrapers/base.py) is an ABC
  with an `@abstractmethod search()`. It defines the *contract* every platform scraper
  must fulfil, and shares helpers (`parse_price`, `max_results`) via inheritance. This is
  the **Strategy pattern**: interchangeable implementations behind one interface, held in
  a registry (`SCRAPERS = {"amazon": AmazonScraper(), ...}`) and looped over uniformly.
- **Packages & modules.** Folders with `__init__.py` are *packages*; `mcp_server`,
  `agent`, `webapp` are the three top-level ones. Imports like
  `from .valuation import evaluate_offer` (the leading dot = "same package") keep the
  structure explicit.
- **`if __name__ == "__main__":`** — the code that runs only when a file is executed
  directly (`python -m mcp_server.server`), not when it's imported. That's how one file
  is both an importable module and a runnable program.
- **Regular expressions.** Used for extracting prices, model codes, and coupon terms
  from free text. Powerful for messy real-world strings — used surgically, not for
  parsing whole HTML documents (that's the parser's job).
- **List/set/dict comprehensions.** `[o.to_dict() for o in offers]`,
  `{w for w in words if ...}` — concise, readable transforms that are idiomatic Python.

---

## 15. Glossary

| Term | One-line meaning |
|------|------------------|
| **Agent** | An LLM in a loop with tools, doing multi-step work autonomously. |
| **Agent loop** | call model → run tool → feed result back → repeat until done. |
| **Tool runner** | SDK helper that runs the agent loop for you. |
| **MCP** | Model Context Protocol — open standard connecting AI models to tools. |
| **MCP server / client** | Provider of tools / consumer of tools, over MCP. |
| **stdio transport** | Client talks to a locally-launched server over stdin/stdout. |
| **Tool schema** | Name + description + typed parameters the model reads to call a tool. |
| **System prompt** | Instructions setting the model's role and rules, separate from user input. |
| **Effort** | Dial for how hard the model deliberates (quality vs cost/latency). |
| **Refusal** | Safety decline returned as a normal response (`stop_reason == "refusal"`). |
| **Scraping** | Fetching web pages and extracting structured data from HTML. |
| **CSS selector** | A query that picks elements out of an HTML document. |
| **Bot wall / CAPTCHA** | Anti-automation defence that blocks scrapers. |
| **Backoff + jitter** | Retry after increasing, randomized delays. |
| **Fail soft** | Return empty/partial results instead of crashing on error. |
| **Jaccard similarity** | shared items ÷ total distinct items; a set-overlap score. |
| **Net effective price** | True cost after coupon + instant discount + rewards. |
| **Stacking** | Applying multiple discounts in the correct order. |
| **Dataclass** | Python class that auto-generates boilerplate from typed fields. |
| **Memoization / cache** | Store a computed result to skip recomputing it. |
| **FastAPI** | Python framework turning typed functions into HTTP endpoints. |
| **SPA** | Single-page app — JS updates the page in place instead of reloading. |
| **Event loop** | The asyncio engine that runs async tasks on one thread. |
| **Feature flag** | Config switch that changes behaviour without code changes. |
| **Separation of concerns** | Each module has one job; change one without breaking others. |

---

*This document describes the code in this repository as built. When you change the
code, update the sections it touches — a concept doc that drifts from the code teaches
the wrong thing.*
