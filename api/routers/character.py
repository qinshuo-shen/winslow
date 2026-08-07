"""
GET /api/character -- character.get_character() + stat_level_cost() per stat
GET /api/character/bloodstain -- bloodstain.get_active_bloodstain()
GET /api/questlines -- questlines.list_active_questlines()

Phase 3 adds POST /api/character/rest (bonfire leveling) --
character.spend_runes_on_stat(), returning the same CharacterOut shape as
the GET (via the shared _build_character_out() below) so the frontend can
just re-render off the response. app.py disables the "Rest" button
client-side (disabled=c.runes < cost) rather than ever hitting the
ValueError path, but this endpoint validates for real (defense in depth --
a disabled button is not a security/integrity boundary) and reports it as
a 400 with spend_runes_on_stat's own message as `detail`.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from procrastination_tool import character, questlines
from procrastination_tool.bloodstain import get_active_bloodstain
from procrastination_tool.config import CHARACTER_STATS, stat_level_cost

from ..schemas import BloodstainOut, CharacterOut, QuestlineOut, StatRestRequest

router = APIRouter(tags=["character"])


def _build_character_out() -> CharacterOut:
    c = character.get_character()
    next_costs = {
        stat_name: stat_level_cost(c.stats.get(stat_name, 0))
        for stat_name in CHARACTER_STATS
    }
    return CharacterOut(runes=c.runes, level=c.level, stats=c.stats, next_costs=next_costs)


@router.get("/character", response_model=CharacterOut)
def get_character_out() -> CharacterOut:
    return _build_character_out()


@router.post("/character/rest", response_model=CharacterOut)
def rest_character(body: StatRestRequest) -> CharacterOut:
    try:
        character.spend_runes_on_stat(body.stat_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _build_character_out()


@router.get("/character/bloodstain", response_model=Optional[BloodstainOut])
def get_bloodstain() -> Optional[BloodstainOut]:
    stain = get_active_bloodstain()
    if stain is None:
        return None
    return BloodstainOut(**stain.__dict__)


@router.get("/questlines", response_model=List[QuestlineOut])
def get_questlines() -> List[QuestlineOut]:
    rows = questlines.list_active_questlines()
    return [
        QuestlineOut(
            project_name=r["project_name"],
            session_count=r["session_count"],
            milestones_paid=r["milestones_paid"],
        )
        for r in rows
    ]
