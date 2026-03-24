# sim/agent.py
# the Agent: personality, inventory, trust, rumors, grudges, goals
# cut from town_sim.py

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sim.config import (
    GOODS, BASE_VALUES, JOB_OUTPUT, JOB_CODE, REFINE_RECIPES,
    TAG_DECAY, GRUDGE_DECAY, GRUDGE_MIN_KEEP, STARVE_GOLD_PENALTY,
    edible_count,
)
from sim.types import MemoryEntry, Rumor, Goal, Grudge


# ╔══════════════════════════════════════════════════════════════╗
# ║ Agent                                                        ║
# ╚══════════════════════════════════════════════════════════════╝

@dataclass
class Agent:
    name: str
    home: Tuple[int, int]
    pos: Tuple[int, int]

    honesty: float
    greed: float
    sociability: float
    vengefulness: float
    memory_depth: int

    town_id: int = 0
    native_town_id: int = 0

    traveling: bool = False
    travel_src: int = 0
    travel_dst: int = 0
    travel_eta: int = 0
    job: str = "farmer"

    gold: float = 80.0
    inv: Dict[str, int] = field(default_factory=dict)

    trust: Dict[str, float] = field(default_factory=dict)
    memory: List[MemoryEntry] = field(default_factory=list)
    rumors: Dict[str, Rumor] = field(default_factory=dict)

    friends: set[str] = field(default_factory=set)
    enemies: set[str] = field(default_factory=set)
    grudges: Dict[str, Grudge] = field(default_factory=dict)
    tags: Dict[str, float] = field(default_factory=dict)
    debts_owed: Dict[str, float] = field(default_factory=dict)
    debts_due: Dict[str, int] = field(default_factory=dict)

    goals: List[Goal] = field(default_factory=list)
    goal_success: Dict[str, int] = field(default_factory=lambda: {"S": 0, "M": 0, "B": 0})
    goal_fail: Dict[str, int] = field(default_factory=lambda: {"S": 0, "M": 0, "B": 0})
    # Soft social class (updated by World each turn)
    status: float = 0.50           # 0..1, smoothed
    social_class: str = "common"   # poor/common/comfortable/elite

    # lifecycle / family
    age: int = 300                 # in months, ~25 years default for initial gen
    lifespan: int = 780            # genetic, ~65 years
    spouse: Optional[str] = None
    children: List[str] = field(default_factory=list)
    parents: Optional[tuple] = None  # (parent_a_name, parent_b_name) or None for founders
    family_id: int = -1
    pregnant_with: Optional[str] = None
    pregnant_due: int = 0
    months_starving: int = 0
    alive: bool = True
    cause_of_death: Optional[str] = None

    def init_inv(self, rng: random.Random) -> None:
        self.inv = {g: 0 for g in GOODS}
        self.inv["food"] = rng.randint(6, 14)

        if self.job == "child":
            return  # children have no starting goods

        if self.job in JOB_OUTPUT:
            g = JOB_OUTPUT[self.job]
            if g != "food":
                self.inv[g] = rng.randint(3, 8)
            return

        if self.job in REFINE_RECIPES:
            _, inputs = REFINE_RECIPES[self.job]
            for g, need in inputs.items():
                self.inv[g] = rng.randint(1, need + 3)
            if self.inv["food"] < 5:
                self.inv["food"] = 5

    def tag_code(self) -> str:
        return JOB_CODE.get(self.job, "UNK")

    def display(self) -> str:
        return f"{self.name}({self.tag_code()})"

    def ensure_trust(self, other_name: str) -> None:
        if other_name == self.name:
            return
        if other_name not in self.trust:
            self.trust[other_name] = 0.50

    def clamp01(self, x: float) -> float:
        return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x

    def remember(self, entry: MemoryEntry) -> None:
        self.memory.append(entry)
        if len(self.memory) > self.memory_depth:
            self.memory = self.memory[-self.memory_depth :]

    def decay_reputation(self) -> None:
        for k in list(self.tags.keys()):
            self.tags[k] *= TAG_DECAY
            if self.tags[k] < 0.05:
                del self.tags[k]

    def add_tag(self, tag: str, strength: float) -> None:
        cur = self.tags.get(tag, 0.0)
        self.tags[tag] = self.clamp01(max(cur, strength))
        if tag == "SCAMMER" and "RELIABLE" in self.tags:
            self.tags["RELIABLE"] *= 0.60
            if self.tags["RELIABLE"] < 0.05:
                del self.tags["RELIABLE"]
        if tag == "RELIABLE" and "SCAMMER" in self.tags:
            self.tags["SCAMMER"] *= 0.60
            if self.tags["SCAMMER"] < 0.05:
                del self.tags["SCAMMER"]

    def add_grudge(self, target: str, *, t: int, strength: float, reason: str) -> None:
        if not target or target == self.name:
            return
        s = self.clamp01(strength)
        g = self.grudges.get(target)
        if g is None:
            self.grudges[target] = Grudge(
                target=target,
                strength=s,
                reason=reason,
                created_t=t,
                last_event_t=t,
            )
            return
        g.strength = self.clamp01(max(g.strength, s))
        g.last_event_t = t
        if reason and reason != g.reason:
            g.reason = reason

    def grudge_strength(self, target: str) -> float:
        g = self.grudges.get(target)
        return 0.0 if g is None else g.strength

    def has_grudge(self, target: str, *, at_least: float = 0.25) -> bool:
        return self.grudge_strength(target) >= at_least

    def decay_grudges(self) -> None:
        for k in list(self.grudges.keys()):
            g = self.grudges[k]
            g.strength *= GRUDGE_DECAY
            if g.strength < GRUDGE_MIN_KEEP:
                del self.grudges[k]

    def tag_strength(self, tag: str) -> float:
        return self.tags.get(tag, 0.0)

    def owes(self, creditor: str) -> float:
        return self.debts_owed.get(creditor, 0.0)

    def add_debt(self, creditor: str, amount: float, due_t: int) -> None:
        if amount <= 0:
            return
        self.debts_owed[creditor] = self.debts_owed.get(creditor, 0.0) + amount
        self.debts_due[creditor] = max(self.debts_due.get(creditor, 0), due_t)

    def pay_debt(self, creditor: str, amt: float) -> float:
        if amt <= 0:
            return 0.0
        owed = self.debts_owed.get(creditor, 0.0)
        if owed <= 0:
            return 0.0
        pay = min(amt, owed, self.gold)
        if pay <= 0:
            return 0.0
        self.gold -= pay
        owed2 = owed - pay
        if owed2 <= 1e-6:
            self.debts_owed.pop(creditor, None)
            self.debts_due.pop(creditor, None)
        else:
            self.debts_owed[creditor] = owed2
        return pay

    def update_rumor(
        self,
        t: int,
        speaker: str,
        subject: str,
        claim: str,
        speaker_trust: float,
        speaker_status: float = 0.50,
    ) -> None:
        key = f"{subject}:{claim}"
        r = self.rumors.get(key)
        if r is None:
            r = Rumor(subject=subject, claim=claim, confidence=0.5, last_updated=t)
            self.rumors[key] = r

        prior = r.confidence
        cred = max(0.70, min(1.30, 1.0 + 0.50 * (speaker_status - 0.50)))
        evidence = (0.5 + 0.45 * (speaker_trust - 0.5)) * cred
        new_conf = 0.70 * prior + 0.30 * evidence

        r.confidence = self.clamp01(new_conf)
        r.last_updated = t
        r.sources[speaker] = max(r.sources.get(speaker, 0.0), speaker_trust)

        self.remember(MemoryEntry(
            t=t, kind="gossip", speaker=speaker, subject=subject, content=claim, confidence=r.confidence
        ))

    def price_estimate(self, good: str, rng: random.Random) -> float:
        base = BASE_VALUES[good]
        noise = rng.uniform(-0.25, 0.25)
        scarcity = 0.0
        if good == "food" and edible_count(self.inv) < 2:
            scarcity = 0.50
        if good == "luxury" and self.inv.get("luxury", 0) == 0:
            scarcity = 0.20
        return max(0.5, base * (1.0 + noise + scarcity))

    def wants_to_talk(self, rng: random.Random) -> bool:
        return rng.random() < self.sociability

    def wants_to_trade(self, rng: random.Random) -> bool:
        if edible_count(self.inv) < 2:
            return True
        return rng.random() < (0.35 + 0.30 * self.greed)

    def step_basic_needs(self) -> None:
        if self.inv.get("food", 0) > 0:
            self.inv["food"] -= 1
            return
        # fallback edible goods
        for alt in ("bread", "jerky", "ale"):
            if self.inv.get(alt, 0) > 0:
                self.inv[alt] -= 1
                return
        self.gold = max(0.0, self.gold - STARVE_GOLD_PENALTY)

    def choose_rumor_to_share(self, rng: random.Random) -> Optional[Rumor]:
        if not self.rumors:
            return None
        items = list(self.rumors.values())
        items.sort(key=lambda r: (abs(r.confidence - 0.5), r.last_updated), reverse=True)
        if rng.random() < 0.75:
            return items[0]
        return rng.choice(items)

    def choose_lie(self, rng: random.Random) -> bool:
        lie_pressure = 0.55 * self.greed + 0.40 * (1.0 - self.honesty)
        return rng.random() < lie_pressure