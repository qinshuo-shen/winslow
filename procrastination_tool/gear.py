"""
The Armory (RPG reward system, Phase E -- see character.py's docstring for
the overall design). Gear is stats-plus-flavor-text only, no sprite/avatar
art -- the user's explicit preference for a "systems/stats-rich" character
over a visual one, at least for v1. Purchases are gated by both character
level and Rune cost, spent from the same unified Rune balance used for
bonfire stat leveling (deliberately kept as one resource, not split
XP/gold -- fewer moving parts to track).

Catalog lives in gear_catalog.json (project root), same user-editable JSON
pattern as spin_wheel_config.json.
"""
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from typing import List

from .config import GEAR_CATALOG_PATH, SESSION_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gear_id TEXT NOT NULL UNIQUE,
    purchased_at TEXT NOT NULL
)
"""


@dataclass
class GearItem:
    gear_id: str
    name: str
    cost: int
    min_level: int
    flavor_text: str


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(SESSION_DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def load_gear_catalog() -> List[GearItem]:
    if not GEAR_CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"Gear catalog not found at {GEAR_CATALOG_PATH} -- see gear_catalog.json in the project root."
        )
    with open(GEAR_CATALOG_PATH) as f:
        data = json.load(f)
    return [
        GearItem(
            gear_id=item["id"], name=item["name"], cost=item["cost"],
            min_level=item.get("min_level", 0), flavor_text=item.get("flavor_text", ""),
        )
        for item in data.get("items", [])
    ]


def list_owned_gear() -> List[str]:
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT gear_id FROM inventory ORDER BY id").fetchall()
    return [r[0] for r in rows]


def purchase_gear(gear_id: str) -> None:
    """Buys `gear_id` if the character meets its level requirement and has
    enough Runes. Raises ValueError otherwise. Import is local to avoid a
    module-level circular import with character.py."""
    from . import character

    catalog = {item.gear_id: item for item in load_gear_catalog()}
    item = catalog.get(gear_id)
    if item is None:
        raise ValueError(f"Unknown gear item {gear_id!r}")
    if gear_id in list_owned_gear():
        raise ValueError(f"Already own {item.name!r}")

    c = character.get_character()
    if c.level < item.min_level:
        raise ValueError(f"Requires character level {item.min_level} (currently {c.level})")
    if c.runes < item.cost:
        raise ValueError(f"Not enough Runes for {item.name!r} (need {item.cost}, have {c.runes})")

    character.award_runes(-item.cost)
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO inventory (gear_id, purchased_at) VALUES (?, ?)",
            (gear_id, datetime.now().isoformat()),
        )
        conn.commit()
