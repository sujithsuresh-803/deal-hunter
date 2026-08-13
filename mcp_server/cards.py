"""Load the payment-card catalogue from data/cards.json."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .models import CardOffer

_DATA = Path(__file__).resolve().parent.parent / "data" / "cards.json"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_cards() -> list[CardOffer]:
    raw = json.loads(_DATA.read_text(encoding="utf-8"))
    cards = [CardOffer(**entry) for entry in raw]
    for c in cards:
        if not c.id:
            c.id = _slug(c.name)
    return cards
