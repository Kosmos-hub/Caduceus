# sim/economy.py
# global market (travelling merchant guild)
# cut from town_sim.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

from sim.config import (
    GOODS, BASE_VALUES,
    MARKET_GOLD_START, MARKET_BASE_POP,
    MERCHANT_PRICE_SENS, MERCHANT_SPREAD,
)


# ╔══════════════════════════════════════════════════════════════╗
# ║ Global Market (travelling merchant guild)                    ║
# ╚══════════════════════════════════════════════════════════════╝

@dataclass
class Market:
    stock: Dict[str, int] = field(default_factory=dict)
    target: Dict[str, int] = field(default_factory=dict)
    gold: float = MARKET_GOLD_START

    production: Dict[str, int] = field(default_factory=dict)
    demand: Dict[str, int] = field(default_factory=dict)

    base_pop: int = MARKET_BASE_POP

    _base_stock: Dict[str, int] = field(default_factory=dict, repr=False)
    _base_target: Dict[str, int] = field(default_factory=dict, repr=False)
    _base_production: Dict[str, int] = field(default_factory=dict, repr=False)
    _base_demand: Dict[str, int] = field(default_factory=dict, repr=False)
    _base_gold: float = field(default=0.0, repr=False)

    price_sensitivity: float = MERCHANT_PRICE_SENS
    spread: float = MERCHANT_SPREAD

    def __post_init__(self) -> None:
        for g in GOODS:
            self.demand.setdefault(g, 0)
            self.stock.setdefault(g, 0)
            self.target.setdefault(g, 40)
            self.production.setdefault(g, 0)

        if not self._base_stock:
            self._base_stock = dict(self.stock)
            self._base_target = dict(self.target)
            self._base_production = dict(self.production)
            self._base_demand = dict(self.demand)
            self._base_gold = float(self.gold)

    def autoscale_for_population(self, pop: int) -> None:
        if pop <= 0:
            return
        base = max(1, int(self.base_pop))
        f = pop / base
        f = 0.25 if f < 0.25 else 12.0 if f > 12.0 else f

        for g, v in self._base_target.items():
            self.target[g] = max(1, int(round(v * f)))
        for g, v in self._base_production.items():
            self.production[g] = max(0, int(round(v * f)))
        for g, v in self._base_demand.items():
            self.demand[g] = max(0, int(round(v * f)))

        desired_gold = float(self._base_gold) * f
        if self.gold < desired_gold:
            self.gold = desired_gold

        for g, v in self._base_stock.items():
            floor = int(round(v * f * 0.60))
            if floor > 0:
                self.stock[g] = max(self.stock.get(g, 0), floor)

        # ensure some baseline drain so base resources don't inflate forever
        for g in ("food", "wood", "ore", "stone", "tools", "cloth"):
            floor = int(round(0.05 * pop))
            if g == "food":
                floor = int(round(0.08 * pop))
            self.demand[g] = max(self.demand.get(g, 0), floor)

    def tick(self) -> None:
        for g, amt in self.production.items():
            if amt > 0:
                self.stock[g] += amt
        for g, d in self.demand.items():
            if d > 0:
                self.stock[g] = max(0, self.stock[g] - d)

    def mid_price(self, good: str) -> float:
        base = BASE_VALUES[good]
        tgt = max(1, self.target[good])
        s = max(0, self.stock[good])
        shortage = (tgt - s) / tgt
        mult = 1.0 + self.price_sensitivity * shortage
        if mult < 0.35:
            mult = 0.35
        if mult > 2.50:
            mult = 2.50
        return base * mult

    def buy_price(self, good: str) -> float:
        return self.mid_price(good) * (1.0 + self.spread)

    def sell_price(self, good: str) -> float:
        return self.mid_price(good) * (1.0 - self.spread)

    def agent_buys(self, good: str, qty: int, agent_gold: float) -> Tuple[int, float]:
        if qty <= 0:
            return 0, 0.0
        have = self.stock.get(good, 0)
        if have <= 0:
            return 0, 0.0

        unit = self.buy_price(good)
        max_afford = int(agent_gold // unit) if unit > 0 else 0
        take = min(qty, have, max_afford)
        if take <= 0:
            return 0, 0.0

        cost = take * unit
        self.stock[good] -= take
        self.gold += cost
        return take, cost

    def agent_sells(self, good: str, qty: int) -> float:
        if qty <= 0:
            return 0.0

        unit = self.sell_price(good)
        max_afford = int(self.gold // unit) if unit > 0 else 0
        sell_qty = min(qty, max_afford)
        if sell_qty <= 0:
            return 0.0

        payout = sell_qty * unit
        self.gold -= payout
        self.stock[good] += sell_qty
        return payout
