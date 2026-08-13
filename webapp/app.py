"""Deal Hunter — web API + front-end.

Wraps the same core engine the MCP/agent path uses, exposed over HTTP so the
single-page front-end can drive it.

Run:  uvicorn webapp.app:app --reload
Then open  http://127.0.0.1:8000
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mcp_server.cards import load_cards
from mcp_server.pipeline import run_pipeline

load_dotenv()

app = FastAPI(title="Deal Hunter", version="1.0")

_STATIC = Path(__file__).resolve().parent / "static"


@app.get("/api/cards")
def cards() -> dict:
    """The selectable card catalogue for the 'cards I own' picker."""
    out = []
    for c in load_cards():
        out.append(
            {
                "id": c.id,
                "name": c.name,
                "network": c.network,
                "notes": c.notes,
                "platforms": sorted(c.instant_discounts.keys()),
                "reward_rate": c.reward_rate,
            }
        )
    return {"cards": out}


@app.get("/api/deal")
def deal(
    query: str = Query(..., min_length=2),
    cards: str | None = Query(None, description="comma-separated card ids you own"),
) -> dict:
    """Run the full pipeline for a product, optionally scoped to owned cards.

    Defined as a sync `def` so FastAPI runs the blocking scrape in a threadpool.
    """
    owned = [c for c in cards.split(",") if c] if cards else None
    return run_pipeline(query, owned_card_ids=owned)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


# Serve everything else in /static (css/js live inline in index.html for now).
app.mount("/static", StaticFiles(directory=_STATIC), name="static")
