# sim/towns.py
# town and expedition meeting structures
# cut from town_sim.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from sim.config import GOODS, MEETING_MIN_FUND


# ╔══════════════════════════════════════════════════════════════╗
# ║ Towns + Expeditions                                          ║
# ╚══════════════════════════════════════════════════════════════╝

@dataclass
class Meeting:
    proposer: str
    town_id: int
    scheduled_t: int
    target_town_id: int
    wanted_good: str
    min_fund: float = MEETING_MIN_FUND
    investments: Dict[str, float] = field(default_factory=dict)
    resolved: bool = False
    succeeded: bool = False
    qty_returned: int = 0

@dataclass
class Town:
    name: str
    town_id: int
    resources: set[str]
    # Not a market: just a rough "local availability" pool that expeditions can tap.
    local_stock: Dict[str, int] = field(default_factory=dict)
    meetings: List[Meeting] = field(default_factory=list)

    def __post_init__(self) -> None:
        for g in GOODS:
            self.local_stock.setdefault(g, 0)

    def has_resource(self, good: str) -> bool:
        return good in self.resources
