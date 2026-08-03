"""
The "spin wheel" reward mechanic (Phase 2).

Design history worth knowing before touching this file: the user's
original idea was an automated *punishment* system that would send
embarrassing "confession" messages to coworkers/friends on a focus lapse.
That was flagged as counterproductive for the user's own motivation and
wellbeing, a consent problem (third parties never agreed to be an
accountability mechanism), and practically risky (irreversible, and could
damage real relationships if used carelessly). The user agreed and
redesigned it themselves into this self-contained wheel instead.

HARD CONSTRAINT, not a style preference: this module may only ever
*suggest* an action via a local notification. It must never hold
credentials or write/send access to Messages, Mail, phone, or any other
channel capable of contacting another person on the user's behalf --
including for the "call a friend"-style items, which are suggestions the
user acts on themselves, not something this code executes. Do not add
any outbound-communication capability here, ever, even for convenience.
"""
import json
import random
from typing import List

from .config import SPIN_WHEEL_CONFIG_PATH


def load_wheel_items() -> List[str]:
    if not SPIN_WHEEL_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Spin wheel config not found at {SPIN_WHEEL_CONFIG_PATH} -- "
            "see spin_wheel_config.json in the project root."
        )
    with open(SPIN_WHEEL_CONFIG_PATH) as f:
        data = json.load(f)
    items = data.get("items", [])
    if not items:
        raise ValueError(f"Spin wheel config at {SPIN_WHEEL_CONFIG_PATH} has no items.")
    return items


def spin() -> str:
    """Pick one random reward suggestion. Does not perform any action -- caller is responsible for displaying it."""
    return random.choice(load_wheel_items())
