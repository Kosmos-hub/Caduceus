# sim/regions.py
# multi-region wrapper
# cut from town_sim.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from sim.economy import Market
from sim.towns import Town
from sim.agent import Agent
from sim.world import World


# ╔══════════════════════════════════════════════════════════════╗
# ║ Regions (multi-world wrapper)                                ║
# ╚══════════════════════════════════════════════════════════════╝

@dataclass
class MultiWorld:
    regions: List[World]
    active_region: int = 0

    def current(self) -> World:
        if not self.regions:
            raise RuntimeError("No regions")
        i = 0 if self.active_region < 0 else (len(self.regions) - 1 if self.active_region >= len(self.regions) else self.active_region)
        return self.regions[i]

    @property
    def t(self) -> int:
        return self.current().t

    @property
    def towns(self) -> List[Town]:
        return self.current().towns

    @property
    def agents(self) -> List[Agent]:
        return self.current().agents

    @property
    def market(self) -> Market:
        return self.current().market

    @property
    def merchant_town_id(self) -> int:
        return self.current().merchant_town_id

    def tick(self) -> List[str]:
        # advance all regions, but only emit logs from the active one
        out: List[str] = []
        for i, r in enumerate(self.regions):
            logs = r.tick()
            if i == self.active_region:
                out = logs
        return out
