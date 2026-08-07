"""GET /api/gear -- catalog + owned + server-computed can_buy, mirroring
app.py's Armory section exactly:
    can_buy = (item.gear_id not in owned) and c.level >= item.min_level and c.runes >= item.cost

Phase 3 adds POST /api/gear/{gear_id}/buy -- gear.purchase_gear(), returning
the same List[GearOut] shape as the GET (via the shared _build_gear_out()
below) so the frontend can re-render the whole Armory off the response.
app.py disables the "Buy" button client-side (disabled=not can_buy) rather
than ever hitting the ValueError path, but this endpoint validates for real
(defense in depth) and reports it as a 400 with purchase_gear's own message
as `detail`.
"""
from typing import List

from fastapi import APIRouter, HTTPException

from procrastination_tool import character, gear

from ..schemas import GearOut

router = APIRouter(tags=["gear"])


def _build_gear_out() -> List[GearOut]:
    owned = set(gear.list_owned_gear())
    c = character.get_character()
    out: List[GearOut] = []
    for item in gear.load_gear_catalog():
        is_owned = item.gear_id in owned
        can_buy = (not is_owned) and c.level >= item.min_level and c.runes >= item.cost
        out.append(GearOut(
            gear_id=item.gear_id, name=item.name, cost=item.cost,
            min_level=item.min_level, flavor_text=item.flavor_text,
            owned=is_owned, can_buy=can_buy,
        ))
    return out


@router.get("/gear", response_model=List[GearOut])
def get_gear() -> List[GearOut]:
    return _build_gear_out()


@router.post("/gear/{gear_id}/buy", response_model=List[GearOut])
def buy_gear(gear_id: str) -> List[GearOut]:
    try:
        gear.purchase_gear(gear_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _build_gear_out()
