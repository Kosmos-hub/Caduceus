# sim/types.py
# core dataclasses shared across the sim
# cut from town_sim.py -- Memory + Beliefs section

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


# ╔══════════════════════════════════════════════════════════════╗
# ║ Memory + Beliefs                                             ║
# ╚══════════════════════════════════════════════════════════════╝

@dataclass
class MemoryEntry:
    t: int
    kind: str
    speaker: str
    subject: str
    content: str
    confidence: float

@dataclass
class Rumor:
    subject: str
    claim: str
    confidence: float
    last_updated: int
    sources: Dict[str, float] = field(default_factory=dict)

    origin_town_id: int = -1
    hops: int = 0

@dataclass
class Goal:
    size: str          # "S", "M", "B"
    good: str
    qty: int
    created_t: int
    deadline_t: int
    interval: int      # 10 / 25 / 50
    reward_gold: float
    penalty_gold: float
    resolved: bool = False
    succeeded: bool = False

@dataclass
class Debt:
    creditor: str
    debtor: str
    amount: float
    created_t: int
    last_payment_t: int
    active: bool = True
    last_rumor_t: int = -10_000
    last_rumor_amt: float = 0.0

@dataclass
class Grudge:
    target: str
    strength: float
    reason: str
    created_t: int
    last_event_t: int
