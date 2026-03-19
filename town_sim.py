# town_sim.py
# Gossip + trade society sim in a multi-town world
# World has: towns with resource profiles, local social networks, expeditions, rumors,
# and ONE global market carried by a travelling Merchant Guild along a route.

from __future__ import annotations

import random
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ╔══════════════════════════════════════════════════════════════╗
# ║ Config                                                       ║
# ╚══════════════════════════════════════════════════════════════╝

GOODS = (
    # base goods
    "food", "wood", "ore", "stone", "tools", "cloth",
    # refined from food
    "bread", "ale", "jerky",
    # refined from wood
    "plank", "charcoal", "furniture",
    # refined from ore
    "ingot", "scimitar", "ring",
    # refined from stone
    "brick", "sculpture",
    # refined from cloth
    "garment", "banner",
    # refined from tools
    "wagon", "lockbox",
    # legacy
    "luxury",
)

BASE_VALUES: Dict[str, float] = {
    # base
    "food": 6.0, "wood": 4.0, "ore": 7.0, "stone": 5.0, "tools": 9.0, "cloth": 8.0,
    # food refiners
    "bread": 10.0, "ale": 12.0, "jerky": 11.0,
    # wood refiners
    "plank": 7.0, "charcoal": 9.0, "furniture": 16.0,
    # ore refiners
    "ingot": 12.0, "scimitar": 22.0, "ring": 26.0,
    # stone refiners
    "brick": 8.0, "sculpture": 18.0,
    # cloth refiners
    "garment": 15.0, "banner": 17.0,
    # tools refiners
    "wagon": 20.0, "lockbox": 18.0,
    # legacy
    "luxury": 14.0,
}

TOWN_W = 12
TOWN_H = 8

SEED = 40
TURNS = 120
NUM_AGENTS = 80

# multi-town
NUM_REGIONS = 4

# per-region towns
NUM_TOWNS = 4
TOWN_POP_MIN = 15
TOWN_POP_MAX = 35

# Town resource profiles
TOWN_RESOURCE_MISS_CHANCE = 0.25  # chance to NOT have a base resource (except food)
TOWN_MIN_RESOURCES = 3
JOB_WAGE = 5

# Merchant Guild: one global market that physically moves town-to-town.
# Each turn it is in exactly one town (route is town0 -> town1 -> ... -> townN-1 -> town0).
# So each town sees the merchant every NUM_TOWNS turns.
MERCHANT_SPREAD = 0.14
MERCHANT_PRICE_SENS = 0.85

# Expeditions / meetings
MEETING_PROPOSE_EVERY = 10
MEETING_HAPPENS_AFTER = 2
MEETING_MIN_FUND = 20.0

# Credit / debt
DEBT_DUE_TURNS = 10
CREDIT_MIN_DOWNPAY = 0.75
CREDIT_MAX_FRACTION_OF_PRICE = 0.70
CREDIT_MAX_ABS = 18.0

# Reputation
TAG_DECAY = 0.97
DEBT_OVERDUE_TAG = 0.65
OVERDUE_RUMOR_COOLDOWN = 6
OVERDUE_RUMOR_REPOST_DELTA = 1.25

# grudges (only spread negative rumors / betray when wronged)
GRUDGE_DECAY = 0.985
GRUDGE_MIN_KEEP = 0.12
GRUDGE_MAX = 1.0

# starvation
STARVE_GOLD_PENALTY = 1.25

# market scaling
MARKET_GOLD_START = 600.0
MARKET_BASE_POP = 80


# ╔══════════════════════════════════════════════════════════════╗
# ║ Jobs                                                         ║
# ╚══════════════════════════════════════════════════════════════╝

JOB_OUTPUT = {
    # producers (base)
    "farmer": "food",
    "lumberjack": "wood",
    "miner": "ore",
    "mason": "stone",
    "weaver": "cloth",
    "crafter": "tools",
}

BASE_OUTPUT_RANGE = {
    "farmer": (2, 4),
    "lumberjack": (2, 4),
    "miner": (2, 3),
    "mason": (2, 3),
    "weaver": (2, 3),
    "crafter": (1, 2),
}

REFINE_RECIPES = {
    # Food
    "baker": ("bread", {"food": 1}),
    "brewer": ("ale", {"food": 1}),
    "butcher": ("jerky", {"food": 1}),
    # Wood
    "sawyer": ("plank", {"wood": 1}),
    "kilnworker": ("charcoal", {"wood": 1}),
    "carpenter": ("furniture", {"plank": 1}),
    # Ore
    "smelter": ("ingot", {"ore": 1}),
    "metalsmith": ("scimitar", {"ingot": 1}),
    "jeweler": ("ring", {"ingot": 1}),
    # Stone
    "brickmaker": ("brick", {"stone": 1}),
    "sculptor": ("sculpture", {"stone": 1}),
    # Cloth
    "tailor": ("garment", {"cloth": 1}),
    "dyer": ("banner", {"cloth": 1}),
    # Tools
    "wheelwright": ("wagon", {"tools": 1}),
    "locksmith": ("lockbox", {"tools": 1}),
}

REFINE_OUTPUT_QTY = {
    "baker": 2,
    "brewer": 2,
    "butcher": 2,
    "sawyer": 2,
    "kilnworker": 2,
    "carpenter": 1,
    "smelter": 2,
    "metalsmith": 1,
    "jeweler": 1,
    "brickmaker": 2,
    "sculptor": 1,
    "tailor": 2,
    "dyer": 1,
    "wheelwright": 1,
    "locksmith": 1,
}

JOB_CODE = {
    **{k: k[:3].upper() for k in JOB_OUTPUT.keys()},
    **{k: k[:3].upper() for k in REFINE_RECIPES.keys()},
}


# ╔══════════════════════════════════════════════════════════════╗
# ║ Goal tiers                                                   ║
# ╚══════════════════════════════════════════════════════════════╝

BASE_GOODS = {"food", "wood", "ore", "stone", "tools", "cloth"}

COMMON_REFINED = {
    "bread", "ale", "jerky",
    "plank", "charcoal",
    "ingot", "brick",
    "garment",
}

RARE_REFINED = {
    "furniture",
    "scimitar", "ring",
    "sculpture",
    "banner",
    "wagon", "lockbox",
    "luxury",
}

def goal_tier(good: str) -> int:
    if good in BASE_GOODS:
        return 0
    if good in COMMON_REFINED:
        return 1
    return 2

EDIBLE_GOODS = ("food", "bread", "jerky", "ale")

def edible_count(inv: Dict[str, int]) -> int:
    return sum(inv.get(g, 0) for g in EDIBLE_GOODS)


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


# ╔══════════════════════════════════════════════════════════════╗
# ║ Name generation                                              ║
# ╚══════════════════════════════════════════════════════════════╝

def _tuaregish_name(rng: random.Random) -> str:
    a = ["a","e","i","o","u","aa","ai","ou","ia","ua"]
    c = ["t","d","k","g","q","h","m","n","r","l","s","z","y","w","f","b","j","gh","kh","sh"]
    starts = ["","a","al","el","ou","ibn","ben","abu","tin","tan","ag","an","ar"]
    mid = ["aman","tader","tamas","assuf","kel","tenere","azzar","imzad","tahoua","tinari","tey","najat",
           "salem","hassan","moussa","zahir","farid","sidi","tarek"]
    ends = ["","a","i","u","an","en","in","oun","ar","ir","at","et","ek","ou","iya"]

    s = rng.choice(starts)
    core = rng.choice(mid)
    if rng.random() < 0.55:
        core = rng.choice(c) + rng.choice(a) + rng.choice(c) + rng.choice(a) + rng.choice(c)
    name = (s + core + rng.choice(ends)).replace("--", "-").strip("-")
    if not name:
        name = rng.choice(mid)
    return name[:1].upper() + name[1:]

def gen_unique_names(rng: random.Random, n: int) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    tries = 0
    while len(out) < n and tries < 20000:
        tries += 1
        nm = _tuaregish_name(rng)
        if nm in seen:
            continue
        seen.add(nm)
        out.append(nm)
    while len(out) < n:
        out.append(f"Name{len(out)+1}")
    return out


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

    gold: float = 30.0
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

    def init_inv(self, rng: random.Random) -> None:
        self.inv = {g: 0 for g in GOODS}
        self.inv["food"] = rng.randint(2, 5)

        if self.job in JOB_OUTPUT:
            g = JOB_OUTPUT[self.job]
            if g != "food":
                self.inv[g] = rng.randint(1, 3)
            return

        if self.job in REFINE_RECIPES:
            _, inputs = REFINE_RECIPES[self.job]
            for g, need in inputs.items():
                self.inv[g] = rng.randint(0, need + 1)
            if self.inv["food"] < 2:
                self.inv["food"] = 2

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


# ╔══════════════════════════════════════════════════════════════╗
# ║ World                                                        ║
# ╚══════════════════════════════════════════════════════════════╝

@dataclass
class World:
    agents: List[Agent]
    towns: List[Town]
    rng: random.Random
    market: Market  # one global market carried by the Merchant Guild
    t: int = 0

    debts: List[Debt] = field(default_factory=list)
    merchant_town_id: int = 0  # where the market currently is

    def __post_init__(self) -> None:
        self.update_social_classes()

    def update_social_classes(self) -> None:
        # Wealth percentile within each town + small prestige nudges.
        prestige = {
            "tailor": 1.0,
            "baker": 0.8,
            "jeweler": 1.5,
            "merchant": 1.4,
            "locksmith": 1.2,
            "carpenter": 1.0,
            "wheelwright": 1.0,
            "metalsmith": 1.2,
            "brewer": 0.9,
            "farmer": 0.5,
            "miner": 0.6,
            "mason": 0.6,
            "weaver": 0.8,
            "crafter": 0.9,
            "lumberjack": 0.5,
            "smelter": 0.9,
            "brickmaker": 0.6,
            "sawyer": 0.6,
            "dyer": 0.7,
            "sculptor": 1.1,
        }

        for tid in range(len(self.towns)):
            local = [a for a in self.agents if a.town_id == tid]
            n = len(local)
            if n == 0:
                continue

            local.sort(key=lambda a: a.gold)
            for i, a in enumerate(local):
                p = i / (n - 1) if n > 1 else 0.5

                pr = prestige.get(a.job, 0.7)
                pr01 = 0.5 + 0.10 * (pr - 0.7)
                if pr01 < 0.0:
                    pr01 = 0.0
                if pr01 > 1.0:
                    pr01 = 1.0

                tag_bias = 0.0
                tag_bias += 0.08 * a.tags.get("RELIABLE", 0.0)
                tag_bias -= 0.10 * a.tags.get("SCAMMER", 0.0)

                target = 0.80 * p + 0.20 * pr01 + tag_bias
                if target < 0.0:
                    target = 0.0
                if target > 1.0:
                    target = 1.0

                a.status = 0.90 * a.status + 0.10 * target

                if a.status < 0.20:
                    a.social_class = "poor"
                elif a.status < 0.55:
                    a.social_class = "common"
                elif a.status < 0.85:
                    a.social_class = "comfortable"
                else:
                    a.social_class = "elite"

    def agent_by_name(self, name: str) -> Agent:
        for a in self.agents:
            if a.name == name:
                return a
        raise KeyError(name)

    def town(self, town_id: int) -> Town:
        return self.towns[town_id]

    def town_of(self, a: Agent) -> Town:
        return self.towns[a.town_id]

    def town_agents(self, town_id: int) -> List[Agent]:
        return [x for x in self.agents if x.town_id == town_id]

    def neighbors(self, a: Agent, radius: int = 2) -> List[Agent]:
        if getattr(a, "traveling", False):
            return []
        ax, ay = a.pos
        out: List[Agent] = []
        for b in self.agents:
            if b.town_id != a.town_id:
                continue
            if b.name == a.name:
                continue
            if getattr(b, "traveling", False):
                continue
            bx, by = b.pos
            if abs(ax - bx) + abs(ay - by) <= radius:
                out.append(b)
        return out

    def merchant_here(self, a: Agent) -> bool:
        return a.town_id == self.merchant_town_id

    def flip_claim(self, claim: str) -> str:
        if "not" in claim:
            return claim.replace("not ", "")
        if "is reliable" in claim:
            return claim.replace("is reliable", "is not reliable")
        if "is not reliable" in claim:
            return claim.replace("is not reliable", "is reliable")
        if "scams" in claim:
            return "does not scam"
        if "does not scam" in claim:
            return "scams"
        return "is not reliable"
    
    def exaggerate_claim(self, claim: str) -> str:
        c = claim
        if "owes " in c and "g" in c:
            return "owes everyone money"
        if c == "scams":
            return "scams travelers"
        if c == "is not reliable":
            return "is totally unreliable"
        if c == "is reliable":
            return "is VERY reliable"
        return c + " (allegedly)"
    
    def maybe_mutate_claim(self, claim: str, *, hops: int, cross_town: bool) -> str:
        p = 0.02 + 0.03 * max(0, hops)
        if cross_town:
            p += 0.06
        if self.rng.random() > p:
            return claim

        c = claim

        if "owes " in c and "g" in c and self.rng.random() < 0.60:
            return "owes everyone money"

        if "scams" in c and self.rng.random() < 0.55:
            return "scams travelers"

        if "is reliable" in c and self.rng.random() < 0.55:
            return "is VERY reliable"

        if "is not reliable" in c and self.rng.random() < 0.55:
            return "is totally unreliable"

        if self.rng.random() < 0.25:
            return c + " (allegedly)"

        return c


    def reputation_modifier(self, other: Agent) -> float:
        scam = other.tag_strength("SCAMMER")
        rel = other.tag_strength("RELIABLE")
        unr = other.tag_strength("UNRELIABLE")
        return (0.12 * rel) - (0.18 * scam) - (0.14 * unr)

    def maybe_offer_credit(self, seller: Agent, buyer: Agent, price: float) -> bool:
        if price <= 0.01:
            return False
        downpay = min(buyer.gold, price)
        if downpay < CREDIT_MIN_DOWNPAY:
            return False
        shortfall = price - downpay
        if shortfall <= 0.01:
            return False
        if shortfall > CREDIT_MAX_ABS:
            return False
        if shortfall > CREDIT_MAX_FRACTION_OF_PRICE * price:
            return False
        seller_trust = seller.trust.get(buyer.name, 0.55)
        buyer_rep = buyer.tag_strength("SCAMMER")
        if buyer_rep > 0.55:
            return False
        base = 0.10 + 0.55 * (seller_trust - 0.5)
        base += 0.15 * seller.honesty
        base -= 0.25 * seller.greed
        base -= 0.40 * buyer_rep
        return self.rng.random() < max(0.0, min(0.75, base))

    # ── Goals ───────────────────────────────────────────────────

    def active_goal(self, a: Agent) -> Optional[Goal]:
        best: Optional[Goal] = None
        best_u = -1.0
        for g in a.goals:
            if g.resolved:
                continue
            turns_left = max(0, g.deadline_t - self.t)
            tier = goal_tier(g.good)
            urgency = (1.0 / (1.0 + turns_left)) * (1.0 + 0.35 * tier)
            if urgency > best_u:
                best_u = urgency
                best = g
        return best

    def goal_need(self, a: Agent) -> Optional[Tuple[str, int, float]]:
        g = self.active_goal(a)
        if g is None:
            return None
        have = a.inv.get(g.good, 0)
        miss = g.qty - have
        if miss <= 0:
            return None
        turns_left = max(0, g.deadline_t - self.t)
        tier = goal_tier(g.good)
        urgency = 1.0 / (1.0 + turns_left)
        urgency *= (1.0 + 0.35 * tier)
        behind = miss / max(1, g.qty)
        urgency *= (0.85 + 0.60 * behind)
        return (g.good, miss, urgency)

    def goal_issue_pass(self) -> None:
        def goal_value(good: str, qty: int, interval: int) -> Tuple[float, float]:
            v = BASE_VALUES[good]
            interval_mult = 1.0 if interval <= 10 else (1.55 if interval <= 25 else 2.20)
            reward = 0.50 * v * qty * interval_mult
            penalty = 0.28 * v * qty * interval_mult
            if reward < 6.0:
                reward = 6.0
            if penalty < 4.0:
                penalty = 4.0
            return reward, penalty

        base = sorted(list(BASE_GOODS))
        common = sorted(list(COMMON_REFINED))
        rare = sorted(list(RARE_REFINED))

        def pick_goal(a: Agent, size: str) -> Tuple[str, int, int]:
            if size == "S":
                prefer: List[str] = []
                if a.job in JOB_OUTPUT:
                    prefer.append(JOB_OUTPUT[a.job])
                prefer.append("food")
                pool = list(dict.fromkeys(prefer + base))
                good = self.rng.choice(pool)
                qty = self.rng.randint(2, 4) if good in BASE_GOODS else 1
                return good, qty, 10
            if size == "M":
                pool = common + base
                good = self.rng.choice(pool)
                tier = goal_tier(good)
                qty = self.rng.randint(2, 5) if tier == 0 else self.rng.randint(1, 2)
                return good, qty, 25
            good = self.rng.choice(rare)
            qty = self.rng.randint(1, 2)
            return good, qty, 50

        for a in self.agents:
            for size, every in (("S", 10), ("M", 25), ("B", 50)):
                if self.t % every != 0:
                    continue
                good, qty, interval = pick_goal(a, size)
                r, p = goal_value(good, qty, interval)
                a.goals.append(Goal(
                    size=size, good=good, qty=qty, created_t=self.t,
                    deadline_t=self.t + interval, interval=interval,
                    reward_gold=r, penalty_gold=p
                ))

    def goal_deadline_pass(self) -> List[str]:
        logs: List[str] = []
        for a in self.agents:
            for g in a.goals:
                if g.resolved or self.t != g.deadline_t:
                    continue
                have = a.inv.get(g.good, 0)
                if have >= g.qty:
                    g.resolved = True
                    g.succeeded = True
                    a.gold += g.reward_gold
                    a.add_tag("RELIABLE", 0.55)
                    a.goal_success[g.size] = a.goal_success.get(g.size, 0) + 1
                    logs.append(f"{a.display()} completed goal: {g.good} x{g.qty} (+{g.reward_gold:.2f}g)")
                    a.remember(MemoryEntry(self.t, "goal_success", a.name, a.name, f"Goal success: {g.good} x{g.qty}", 1.0))
                else:
                    g.resolved = True
                    g.succeeded = False
                    a.gold = max(0.0, a.gold - g.penalty_gold)
                    a.add_tag("UNRELIABLE", 0.55)
                    a.goal_fail[g.size] = a.goal_fail.get(g.size, 0) + 1
                    logs.append(f"{a.display()} failed goal: {g.good} x{g.qty} (-{g.penalty_gold:.2f}g)")
                    a.remember(MemoryEntry(self.t, "goal_fail", a.name, a.name, f"Goal failed: {g.good} x{g.qty} (had {have})", 1.0))
                    for b in self.agents:
                        if b.name == a.name:
                            continue
                        if b.town_id != a.town_id:
                            continue
                        if a.name not in b.trust:
                            continue
                        if abs(b.pos[0] - a.pos[0]) + abs(b.pos[1] - a.pos[1]) > 3:
                            continue
                        b.trust[a.name] = max(0.0, b.trust[a.name] - 0.02)

            # keep history bounded
            if len(a.goals) > 80:
                keep = []
                resolved = []
                for gg in a.goals:
                    (resolved if gg.resolved else keep).append(gg)
                a.goals = keep + resolved[-40:]

        return logs

    # ── Town stock (for expeditions) ────────────────────────────

    def town_stock_tick(self) -> None:
        # A small, abstracted supply pool per town that expeditions can tap.
        # It is NOT a market; agents don't directly buy/sell from it each day.
        for town in self.towns:
            pop = len(self.town_agents(town.town_id))
            # produce base resources that exist in town profile
            for g in town.resources:
                if g in BASE_GOODS:
                    town.local_stock[g] += max(1, int(round(0.05 * pop)))
            # drain (local consumption / spoilage)
            town.local_stock["food"] = max(0, town.local_stock["food"] - max(1, int(round(0.04 * pop))))
            # mild decay on other base resources
            for g in ("wood", "ore", "stone", "tools", "cloth"):
                town.local_stock[g] = max(0, town.local_stock[g] - int(round(0.01 * pop)))

    # ── Work / trade / talk ────────────────────────────────────

    def work_and_maybe_sell(self, a: Agent) -> Optional[str]:
        # Pay wage every turn for showing up to work
        a.gold += JOB_WAGE
        made_good: Optional[str] = None

        if a.job in REFINE_RECIPES:
            out_good, inputs = REFINE_RECIPES[a.job]
            can = True
            for g, need in inputs.items():
                if a.inv.get(g, 0) < need:
                    can = False
                    break
            if can:
                for g, need in inputs.items():
                    a.inv[g] -= need
                qty = REFINE_OUTPUT_QTY.get(a.job, 1)
                a.inv[out_good] = a.inv.get(out_good, 0) + qty
                made_good = out_good
                a.remember(MemoryEntry(self.t, "work", a.name, a.name, f"Refined {out_good} x{qty}", 1.0))
            else:
                a.remember(MemoryEntry(self.t, "work", a.name, a.name, "Could not refine (missing inputs)", 1.0))
        else:
            good = JOB_OUTPUT.get(a.job, "food")
            lo, hi = BASE_OUTPUT_RANGE.get(a.job, (1, 1))
            qty = self.rng.randint(lo, hi)
            a.inv[good] = a.inv.get(good, 0) + qty
            made_good = good
            a.remember(MemoryEntry(self.t, "work", a.name, a.name, f"Produced {good} x{qty}", 1.0))

        # Merchant is the only market interface. If he's here, agents may sell a bit.
        if made_good is not None and self.merchant_here(a):
            if made_good in ("food", "wood", "ore", "stone", "cloth", "tools"):
                sell_chance = 0.80 + 0.15 * a.greed
            else:
                sell_chance = 0.20 + 0.60 * a.greed

            if made_good == "food" and edible_count(a.inv) <= 2:
                sell_chance *= 0.35

            # Don't sell reserved goal items unless desperate for food cash.
            reserved = 0
            for goal in a.goals:
                if (not goal.resolved) and goal.good == made_good:
                    reserved = max(reserved, int(goal.qty))

            desperate_for_food = False
            if edible_count(a.inv) <= 0:
                desperate_for_food = a.gold < self.market.buy_price("food")

            if reserved > 0:
                if (not desperate_for_food) and (a.inv.get(made_good, 0) <= reserved):
                    return None

            if self.rng.random() < sell_chance and a.inv.get(made_good, 0) > 0:
                have = a.inv.get(made_good, 0)
                extra = max(0, have - reserved)

                if made_good == "food":
                    keep_food = 3
                    extra = max(0, have - max(keep_food, reserved))

                if desperate_for_food:
                    extra = min(extra, 1)

                if extra <= 0:
                    return None

                if made_good == "food":
                    qty = 1 if extra == 1 else self.rng.randint(max(1, min(2, extra)), min(8, extra))
                elif made_good in ("wood", "ore", "stone", "cloth", "tools"):
                    qty = 1 if extra == 1 else self.rng.randint(1, min(6, extra))
                else:
                    qty = 1 if extra == 1 else self.rng.randint(1, min(4, extra))
                revenue = self.market.agent_sells(made_good, qty)
                sold_qty = int(round(revenue / self.market.sell_price(made_good))) if self.market.sell_price(made_good) > 0 else 0
                sold_qty = min(qty, sold_qty, a.inv.get(made_good, 0))

                if sold_qty <= 0:
                    return None

                a.inv[made_good] -= sold_qty
                a.gold += revenue
                a.remember(MemoryEntry(self.t, "market_sell", "Merchant", "Market", f"Sold {made_good} x{sold_qty} for {revenue:.2f}", 1.0))
                return f"{a.display()} sold {made_good} x{sold_qty} to Merchant for {revenue:.2f}"

        return None

    def trust_adjust(self, a: Agent, other: str, delta: float) -> None:
        a.ensure_trust(other)
        a.trust[other] = a.clamp01(a.trust[other] + delta)

    def talk(self, speaker: Agent, listener: Agent) -> str:
        speaker.ensure_trust(listener.name)
        listener.ensure_trust(speaker.name)

        # Social bonding
        if self.rng.random() < (0.10 + 0.12 * speaker.sociability):
            speaker.friends.add(listener.name)
            listener.friends.add(speaker.name)
            self.trust_adjust(speaker, listener.name, +0.06)
            self.trust_adjust(listener, speaker.name, +0.06)
            speaker.remember(MemoryEntry(self.t, "befriend", speaker.name, listener.name, "positive chat", 1.0))
            listener.remember(MemoryEntry(self.t, "befriend", listener.name, speaker.name, "positive chat", 1.0))
            return f"{speaker.display()} bonded with {listener.display()}"

        # Conflict
        if self.rng.random() < (0.06 + 0.10 * speaker.vengefulness):
            listener.add_grudge(speaker.name, t=self.t, strength=0.45, reason="started drama")
            speaker.add_grudge(listener.name, t=self.t, strength=0.25, reason="got pushed back")
            self.trust_adjust(speaker, listener.name, -0.08)
            self.trust_adjust(listener, speaker.name, -0.10)
            if listener.trust.get(speaker.name, 0.5) < 0.25:
                listener.enemies.add(speaker.name)
            if speaker.trust.get(listener.name, 0.5) < 0.25:
                speaker.enemies.add(listener.name)
            speaker.remember(MemoryEntry(self.t, "aggravate", speaker.name, listener.name, "started drama", 1.0))
            listener.remember(MemoryEntry(self.t, "aggravate", listener.name, speaker.name, "got annoyed", 1.0))
            return f"{speaker.display()} aggravated {listener.display()}"

        # No beef -> no slander. Just normal small talk.
        targets = [k for k, g in speaker.grudges.items() if g.strength >= 0.25 and k != listener.name]
        if not targets:
            speaker.remember(MemoryEntry(self.t, "chat", speaker.name, listener.name, "small talk", 1.0))
            listener.remember(MemoryEntry(self.t, "chat", listener.name, speaker.name, "small talk", 1.0))
            return f"{speaker.display()} chatted with {listener.display()}"

        target = self.rng.choice(targets)

        # Prefer a real rumor the speaker already holds about the target
        pool = [r for r in speaker.rumors.values() if r.subject == target]
        rumor = None
        if pool:
            pool.sort(key=lambda r: (r.confidence, r.last_updated), reverse=True)
            rumor = pool[0]

        if rumor is not None:
            subject = rumor.subject
            claim = rumor.claim
        else:
            subject = target
            claim = "is not reliable"
            key0 = f"{subject}:{claim}"
            speaker.rumors[key0] = Rumor(
                subject=subject,
                claim=claim,
                confidence=0.60,
                last_updated=self.t,
                origin_town_id=int(speaker.town_id),
                hops=0,
            )

        # Only lie/exaggerate if the speaker actually holds a grudge
        will_lie = speaker.choose_lie(self.rng) and (speaker.grudge_strength(target) >= 0.45)
        if will_lie:
            if self.rng.random() < 0.65:
                claim = self.exaggerate_claim(claim)
            else:
                claim = self.flip_claim(claim)

        # If you don't have a grudge, you mostly just vibe (no reputation warfare).
        # If you DO have one, you might quietly poison the well.
        speaker_trust = listener.trust[speaker.name]
        influence = 0.85 + 0.30 * (getattr(speaker, "status", 0.5) - getattr(listener, "status", 0.5))
        if influence < 0.60:
            influence = 0.60
        if influence > 1.20:
            influence = 1.20

        speaker_trust = listener.clamp01(speaker_trust * influence)

        # pick a target only from grudges
        if not speaker.grudges or self.rng.random() > (0.12 + 0.35 * speaker.sociability):
            speaker.remember(MemoryEntry(self.t, "chat", speaker.name, listener.name, "small talk", 1.0))
            listener.remember(MemoryEntry(self.t, "chat", listener.name, speaker.name, "small talk", 1.0))
            return f"{speaker.display()} chatted with {listener.display()}"

        targets = sorted(speaker.grudges.values(), key=lambda g: (g.strength, g.last_event_t), reverse=True)
        tgt = targets[0]
        subject = tgt.target

        # only negative claims here, since this is “grudge talk”
        claim = "is not reliable"
        if "scam" in tgt.reason:
            claim = "scams"
        if "debt" in tgt.reason or "owes" in tgt.reason:
            claim = "owes people money"

        # hide the grudge: sometimes it’s subtle, sometimes it’s spicy
        if self.rng.random() < (0.25 + 0.45 * tgt.strength):
            claim = self.exaggerate_claim(claim)

        listener.update_rumor(self.t, speaker.name, subject, claim, speaker_trust, speaker.status)
        meta = {
            "kind": "gossip",
            "t": self.t,
            "speaker": speaker.name,
            "listener": listener.name,
            "subject": subject,
            "claim": claim,
            "speaker_town": int(speaker.town_id),
            "listener_town": int(listener.town_id),
        }
        msg = f"{speaker.display()} hinted to {listener.display()}: '{subject} {claim}'"
        return msg + " ⟦META:" + json.dumps(meta, separators=(",", ":")) + "⟧"




    def trade(self, a: Agent, b: Agent) -> Optional[str]:
        a.ensure_trust(b.name)
        b.ensure_trust(a.name)

        a_need_food = edible_count(a.inv) < 2
        b_need_food = edible_count(b.inv) < 2

        if a_need_food and b.inv["food"] > 0:
            buyer, seller, good = a, b, "food"
        elif b_need_food and a.inv["food"] > 0:
            buyer, seller, good = b, a, "food"
        else:
            # pick a goal-driven trade if possible
            picked = self._choose_goal_trade(a, b)
            if picked is None:
                return None
            buyer, seller, good = picked

        if seller.inv.get(good, 0) <= 0:
            return None

        buyer_price = buyer.price_estimate(good, self.rng)
        seller_price = seller.price_estimate(good, self.rng)

        buyer_trust = buyer.trust[seller.name]
        seller_trust = seller.trust[buyer.name]

        rep_mod = self.reputation_modifier(seller)

        buyer_max = buyer_price * (0.85 + 0.35 * buyer_trust) * (0.95 + 0.20 * buyer.greed)
        seller_min = seller_price * (0.85 + 0.35 * (1.0 - seller_trust)) * (0.90 + 0.25 * seller.greed)

        buyer_max *= (1.0 + rep_mod)
        seller_min *= (1.0 - 0.07 * seller.tag_strength("RELIABLE")) * (1.0 + 0.18 * seller.tag_strength("SCAMMER"))

        if seller.choose_lie(self.rng):
            seller_min *= 1.12
        if buyer.choose_lie(self.rng):
            buyer_max *= 0.92

        price = max(0.01, 0.55 * seller_min + 0.45 * buyer_max)

        # Scam option
        if buyer.gold + 1e-6 >= price:
            scam_p = 0.04 + 0.25 * seller.greed + 0.25 * (1.0 - seller.honesty) + 0.20 * seller.tag_strength("SCAMMER")
            scam_p -= 0.22 * buyer_trust
            scam_p = 0.0 if scam_p < 0.0 else 0.55 if scam_p > 0.55 else scam_p
            if self.rng.random() < scam_p:
                buyer.gold -= price
                seller.gold += price
                self.trust_adjust(buyer, seller.name, -0.22)
                seller.add_tag("SCAMMER", 0.75)
                buyer.enemies.add(seller.name)
                buyer.add_grudge(seller.name, strength=0.85, t=self.t, reason="got scammed")
                claim = "scams"
                buyer.rumors[f"{seller.name}:{claim}"] = Rumor(
                    subject=seller.name, claim=claim, confidence=0.80, last_updated=self.t,
                    origin_town_id=int(buyer.town_id), hops=0
                )
                buyer.remember(MemoryEntry(self.t, "trade_scammed", seller.name, seller.name, f"Paid {price:.2f} for {good} but got nothing", 1.0))
                seller.remember(MemoryEntry(self.t, "trade_scam", buyer.name, buyer.name, f"Scammed {buyer.name} for {price:.2f}", 1.0))
                meta = {
                    "kind": "trade_scam",
                    "t": self.t,
                    "buyer": buyer.name,
                    "seller": seller.name,
                    "good": good,
                    "price": float(price),
                    "buyer_town": int(buyer.town_id),
                    "seller_town": int(seller.town_id),
                }
                msg = f"{seller.display()} SCAMMED {buyer.display()} (took {price:.2f}g, no {good})"
                return msg + " ⟦META:" + json.dumps(meta, separators=(",", ":")) + "⟧"


        if buyer.gold + 1e-6 < price:
            if self.maybe_offer_credit(seller, buyer, price):
                downpay = min(buyer.gold, price)
                shortfall = price - downpay
                buyer.gold -= downpay
                seller.gold += downpay
                seller.inv[good] -= 1
                buyer.inv[good] = buyer.inv.get(good, 0) + 1
                due = self.t + DEBT_DUE_TURNS
                buyer.add_debt(seller.name, shortfall, due)
                self.debts.append(Debt(
                    creditor=seller.name, debtor=buyer.name, amount=shortfall,
                    created_t=self.t, last_payment_t=self.t, active=True
                ))
                buyer.remember(MemoryEntry(self.t, "trade_credit", seller.name, seller.name, f"Bought {good} on credit, paid {downpay:.2f}, owes {shortfall:.2f}", buyer_trust))
                seller.remember(MemoryEntry(self.t, "trade_credit", buyer.name, buyer.name, f"Sold {good} on credit, got {downpay:.2f}, is owed {shortfall:.2f}", seller_trust))
                self.trust_adjust(buyer, seller.name, +0.01)
                self.trust_adjust(seller, buyer.name, +0.02)
                buyer.add_tag("RELIABLE", 0.55)
                meta = {
                    "kind": "trade_credit",
                    "t": self.t,
                    "buyer": buyer.name,
                    "seller": seller.name,
                    "good": good,
                    "downpay": float(downpay),
                    "shortfall": float(shortfall),
                    "buyer_town": int(buyer.town_id),
                    "seller_town": int(seller.town_id),
                }
                msg = f"{buyer.display()} bought {good} from {seller.display()} on CREDIT (paid {downpay:.2f}, owes {shortfall:.2f})"
                return msg + " ⟦META:" + json.dumps(meta, separators=(",", ":")) + "⟧"
            self.trust_adjust(buyer, seller.name, -0.04)
            self.trust_adjust(seller, buyer.name, -0.02)
            return None

        seller_have = seller.inv.get(good, 0)
        buyer_need_qty = 1

        if good == "food":
            buyer_need_qty = max(1, min(4, 4 - edible_count(buyer.inv)))
        else:
            need = self.goal_need(buyer)
            if need is not None and need[0] == good:
                buyer_need_qty = max(1, min(4, need[1]))
            else:
                buyer_need_qty = 1

        max_afford_qty = int(buyer.gold // price) if price > 0 else 0
        qty = min(seller_have, buyer_need_qty, max_afford_qty)

        if qty <= 0:
            return None

        total_price = price * qty

        buyer.gold -= total_price
        seller.gold += total_price
        seller.inv[good] -= qty
        buyer.inv[good] = buyer.inv.get(good, 0) + qty

        buyer.remember(MemoryEntry(self.t, "trade", seller.name, seller.name, f"Bought {good} x{qty} for {total_price:.2f}", buyer_trust))
        seller.remember(MemoryEntry(self.t, "trade", buyer.name, buyer.name, f"Sold {good} x{qty} for {total_price:.2f}", seller_trust))
        self.trust_adjust(buyer, seller.name, +0.02)
        self.trust_adjust(seller, buyer.name, +0.01)

        if self.rng.random() < 0.10 and seller.tag_strength("SCAMMER") < 0.10:
            seller.add_tag("RELIABLE", 0.55)

        meta = {
            "kind": "trade",
            "t": self.t,
            "buyer": buyer.name,
            "seller": seller.name,
            "good": good,
            "qty": int(qty),
            "price": float(total_price),
            "buyer_town": int(buyer.town_id),
            "seller_town": int(seller.town_id),
        }
        msg = f"{buyer.display()} bought {good} x{qty} from {seller.display()} for {total_price:.2f}"
        return msg + " ⟦META:" + json.dumps(meta, separators=(",", ":")) + "⟧"


    def _choose_goal_trade(self, a: Agent, b: Agent) -> Optional[Tuple[Agent, Agent, str]]:
        a_need = self.goal_need(a)
        b_need = self.goal_need(b)

        if a_need is not None:
            g, _, _ = a_need
            if b.inv.get(g, 0) > 0:
                return (a, b, g)
        if b_need is not None:
            g, _, _ = b_need
            if a.inv.get(g, 0) > 0:
                return (b, a, g)

        if a_need is not None and b_need is not None:
            ag, _, aurg = a_need
            bg, _, burg = b_need
            a_can = b.inv.get(ag, 0) > 0
            b_can = a.inv.get(bg, 0) > 0
            if a_can and b_can:
                return (a, b, ag) if aurg >= burg else (b, a, bg)
        return None

    # ── Merchant market interactions ────────────────────────────

    def market_buy_food_if_needed(self, a: Agent) -> Optional[str]:
        if not self.merchant_here(a):
            return None
        need = 3 - edible_count(a.inv)
        if need <= 0:
            return None
        got, cost = self.market.agent_buys("food", qty=need, agent_gold=a.gold)
        if got <= 0:
            return None
        a.gold -= cost
        a.inv["food"] += got
        a.remember(MemoryEntry(self.t, "market_buy", "Merchant", "Market", f"Bought food x{got} for {cost:.2f}", 1.0))
        return f"{a.display()} bought food x{got} from Merchant for {cost:.2f}"

    def market_buy_inputs_if_refiner(self, a: Agent) -> Optional[str]:
        if not self.merchant_here(a):
            return None
        if a.job not in REFINE_RECIPES:
            return None
        out_good, inputs = REFINE_RECIPES[a.job]
        bought: List[str] = []
        for g, need in inputs.items():
            have = a.inv.get(g, 0)
            miss = need - have
            if miss <= 0:
                continue
            got, cost = self.market.agent_buys(g, qty=miss, agent_gold=a.gold)
            if got <= 0:
                continue
            a.gold -= cost
            a.inv[g] = a.inv.get(g, 0) + got
            a.remember(MemoryEntry(self.t, "market_buy", "Merchant", "Market", f"Bought {g} x{got} for {cost:.2f}", 1.0))
            bought.append(f"{g} x{got} for {cost:.2f}")
        if not bought:
            return None
        return f"{a.display()} bought inputs for {out_good}: " + ", ".join(bought)

    def market_buy_goal_if_needed(self, a: Agent) -> Optional[str]:
        if not self.merchant_here(a):
            return None
        need = self.goal_need(a)
        if need is None:
            return None
        good, miss, urgency = need
        act_p = 0.15 + 0.85 * max(0.0, min(1.0, urgency))
        if self.rng.random() > act_p:
            return None
        want = 1 if miss == 1 else self.rng.randint(1, min(3, miss))
        got, cost = self.market.agent_buys(good, qty=want, agent_gold=a.gold)
        if got <= 0:
            return None
        a.gold -= cost
        a.inv[good] = a.inv.get(good, 0) + got
        a.remember(MemoryEntry(self.t, "market_buy_goal", "Merchant", "Market", f"Bought {good} x{got} for {cost:.2f}", 1.0))
        return f"{a.display()} bought goal {good} x{got} from Merchant for {cost:.2f}"

    def market_sell_excess(self, a: Agent) -> Optional[str]:
        if not self.merchant_here(a):
            return None

        desperate_for_food = False
        if edible_count(a.inv) <= 0:
            desperate_for_food = a.gold < self.market.buy_price("food")

        did_any = False
        sold_lines: List[str] = []
        for g in GOODS:
            base_keep = 4 if g == "food" else 1

            reserved = 0
            for goal in a.goals:
                if (not goal.resolved) and goal.good == g:
                    reserved = max(reserved, int(goal.qty))
            keep = base_keep if (reserved > 0 and desperate_for_food) else max(base_keep, reserved)

            extra = a.inv.get(g, 0) - keep
            if extra <= 0:
                continue
            sell_bias = 0.20 + 0.65 * a.greed
            if g in ("food", "wood", "ore", "stone", "cloth", "tools"):
                sell_bias = 0.75 + 0.20 * a.greed

            if self.rng.random() > sell_bias:
                continue

            if g == "food":
                qty = 1 if extra == 1 else self.rng.randint(max(1, min(2, extra)), min(8, extra))
            elif g in ("wood", "ore", "stone", "cloth", "tools"):
                qty = 1 if extra == 1 else self.rng.randint(1, min(6, extra))
            else:
                qty = 1 if extra == 1 else self.rng.randint(1, min(3, extra))

            unit = self.market.sell_price(g)
            max_sell = int(self.market.gold // unit) if unit > 0 else 0
            sold_qty = min(qty, extra, max_sell)

            if sold_qty <= 0:
                continue

            revenue = self.market.agent_sells(g, sold_qty)
            if revenue <= 0:
                continue

            a.inv[g] -= sold_qty
            a.gold += revenue
            a.remember(MemoryEntry(self.t, "market_sell", "Merchant", "Market", f"Sold {g} x{sold_qty} for {revenue:.2f}", 1.0))
            sold_lines.append(f"{g} x{sold_qty} for {revenue:.2f}")
            did_any = True

        if not did_any:
            return None
        return f"{a.display()} sold to Merchant: " + ", ".join(sold_lines)

    # ── Debts ──────────────────────────────────────────────────

    def maybe_repay_local_debts(self, debtor: Agent, local: List[Agent]) -> Optional[str]:
        if not debtor.debts_owed:
            return None
        creditors_here = {x.name: x for x in local}
        paid_lines: List[str] = []
        for cred_name in list(debtor.debts_owed.keys()):
            if cred_name not in creditors_here:
                continue
            if debtor.gold <= 0.01:
                break
            creditor = creditors_here[cred_name]
            owed = debtor.owes(cred_name)
            want = min(owed, max(2.0, 0.20 * debtor.gold))
            paid = debtor.pay_debt(cred_name, want)
            if paid <= 0:
                continue
            creditor.gold += paid
            creditor.add_tag("RELIABLE", 0.55)
            paid_lines.append(f"{cred_name} {paid:.2f}")

            for d in self.debts:
                if d.active and d.creditor == cred_name and d.debtor == debtor.name:
                    d.amount = max(0.0, d.amount - paid)
                    d.last_payment_t = self.t
                    if d.amount <= 1e-6:
                        d.active = False
            if debtor.owes(cred_name) <= 0.0:
                creditor.grudges.pop(debtor.name, None)

            debtor.remember(MemoryEntry(self.t, "debt_pay", cred_name, cred_name, f"Paid debt {paid:.2f}", 1.0))
            creditor.remember(MemoryEntry(self.t, "debt_recv", debtor.name, debtor.name, f"Received debt payment {paid:.2f}", 1.0))
            self.trust_adjust(debtor, cred_name, +0.02)
            self.trust_adjust(creditor, debtor.name, +0.02)

        if not paid_lines:
            return None
        return f"{debtor.display()} repaid debts: " + ", ".join(paid_lines)

    def debt_overdue_pass(self) -> List[str]:
        logs: List[str] = []
        for d in self.debts:
            if not d.active:
                continue
            if self.t <= d.created_t + DEBT_DUE_TURNS:
                continue
            debtor = self.agent_by_name(d.debtor)
            creditor = self.agent_by_name(d.creditor)
            still_owed = debtor.owes(creditor.name)
            if still_owed <= 0:
                d.active = False
                continue

            cooldown_ok = (self.t - d.last_rumor_t) >= OVERDUE_RUMOR_COOLDOWN
            delta_ok = abs(still_owed - d.last_rumor_amt) >= OVERDUE_RUMOR_REPOST_DELTA
            if not cooldown_ok and not delta_ok:
                continue

            if self.rng.random() < (0.22 + 0.35 * creditor.vengefulness):
                debtor.add_tag("SCAMMER", DEBT_OVERDUE_TAG)
                claim = f"owes {creditor.name} {still_owed:.2f}g"
                creditor.rumors[f"{debtor.name}:{claim}"] = Rumor(
                    subject=debtor.name, claim=claim, confidence=0.75, last_updated=self.t,
                    origin_town_id=int(creditor.town_id), hops=0
                )
                creditor.remember(MemoryEntry(self.t, "debt_overdue", creditor.name, debtor.name, f"{debtor.name} {claim}", 1.0))
                meta = {
                    "kind": "gossip",
                    "t": self.t,
                    "speaker": creditor.name,
                    "listener": "(crowd)",
                    "subject": debtor.name,
                    "claim": claim,
                    "speaker_town": int(creditor.town_id),
                    "listener_town": int(creditor.town_id),
                }
                msg = f"{creditor.display()} started spreading: '{debtor.name} {claim}'"
                logs.append(msg + " ⟦META:" + json.dumps(meta, separators=(",", ":")) + "⟧")
                self.trust_adjust(creditor, debtor.name, -0.10)
                self.trust_adjust(debtor, creditor.name, -0.06)
                d.last_rumor_t = self.t
                d.last_rumor_amt = still_owed

        return logs

    # ── Expeditions / meetings ──────────────────────────────────

    def meeting_pass(self) -> List[str]:
        logs: List[str] = []
        base = ["food", "wood", "ore", "stone", "tools", "cloth"]

        # propose meetings periodically (per town)
        if self.t % MEETING_PROPOSE_EVERY == 0:
            for town in self.towns:
                agents = self.town_agents(town.town_id)
                if not agents:
                    continue
                proposer = max(agents, key=lambda x: (x.status, x.gold))
                missing = [g for g in base if g not in town.resources]
                if not missing:
                    continue
                wanted = self.rng.choice(missing)
                candidates = [t for t in self.towns if t.town_id != town.town_id and wanted in t.resources]
                if not candidates:
                    continue
                target = self.rng.choice(candidates)
                meet_t = self.t + MEETING_HAPPENS_AFTER
                town.meetings.append(Meeting(
                    proposer=proposer.name, town_id=town.town_id, scheduled_t=meet_t,
                    target_town_id=target.town_id, wanted_good=wanted
                ))
                logs.append(f"{town.name}: {proposer.display()} proposed expedition for {wanted} (t={meet_t})")

        # resolve meetings scheduled now
        for town in self.towns:
            for m in town.meetings:
                if m.resolved or m.scheduled_t != self.t:
                    continue
                agents = self.town_agents(town.town_id)
                if not agents:
                    m.resolved = True
                    continue

                pool = 0.0
                proposer_name = m.proposer
                for a in agents:
                    if a.gold < 3.0:
                        continue
                    trust = a.trust.get(proposer_name, 0.5)
                    if trust < 0.42:
                        continue
                    contrib = a.gold * (0.03 + 0.04 * trust)
                    if contrib > a.gold - 1.0:
                        contrib = max(0.0, a.gold - 1.0)
                    if contrib <= 0.0:
                        continue
                    a.gold -= contrib
                    m.investments[a.name] = m.investments.get(a.name, 0.0) + contrib
                    pool += contrib

                if pool < m.min_fund:
                    # refund
                    for inv_name, amt in m.investments.items():
                        inv = next((x for x in agents if x.name == inv_name), None)
                        if inv is not None:
                            inv.gold += amt
                    m.resolved = True
                    m.succeeded = False
                    logs.append(f"{town.name}: expedition meeting failed (not enough funding)")
                    continue

                target = self.towns[m.target_town_id]

                # source from target local_stock first (cheap), else from merchant market (expensive)
                wanted = m.wanted_good
                # cheap unit price is base (represents direct inter-town trade)
                unit_price = BASE_VALUES[wanted] * 0.95
                qty = int(pool / max(0.2, unit_price))
                qty = max(1, qty)

                got_from_target = min(qty, target.local_stock.get(wanted, 0))
                qty_left = qty - got_from_target
                if got_from_target > 0:
                    target.local_stock[wanted] -= got_from_target

                got_from_merchant = 0
                spent = got_from_target * unit_price
                if qty_left > 0:
                    # buy remaining from merchant market at full buy price
                    unit_m = self.market.buy_price(wanted)
                    afford = int((pool - spent) / max(0.2, unit_m))
                    take = min(qty_left, afford)
                    if take > 0:
                        take2, cost2 = self.market.agent_buys(wanted, take, pool - spent)
                        got_from_merchant = take2
                        spent += cost2

                total_got = got_from_target + got_from_merchant
                if total_got <= 0:
                    # refund
                    for inv_name, amt in m.investments.items():
                        inv = next((x for x in agents if x.name == inv_name), None)
                        if inv is not None:
                            inv.gold += amt
                    m.resolved = True
                    m.succeeded = False
                    logs.append(f"{town.name}: expedition failed (couldn't source {wanted})")
                    continue

                leftover = max(0.0, pool - spent)
                profit = spent * 0.10
                payout_pool = leftover + profit

                total_inv = sum(m.investments.values())
                # Distribute goods directly to investors (so goals can complete)
                remaining_goods = total_got
                for inv_name, amt in sorted(m.investments.items(), key=lambda kv: kv[1], reverse=True):
                    inv = next((x for x in agents if x.name == inv_name), None)
                    if inv is None:
                        continue
                    share = amt / total_inv if total_inv > 0 else 0.0
                    inv.gold += payout_pool * share
                    give = int(round(total_got * share))
                    give = min(give, remaining_goods)
                    if give > 0:
                        inv.inv[wanted] = inv.inv.get(wanted, 0) + give
                        remaining_goods -= give

                # any leftovers go to town stock (not a market, just availability)
                if remaining_goods > 0:
                    town.local_stock[wanted] += remaining_goods

                m.resolved = True
                m.succeeded = True
                m.qty_returned = total_got
                logs.append(f"{town.name}: expedition returned {wanted} x{total_got}")

        return logs
    
        # ── Travel / migration ──────────────────────────────────────

    def travel_distance(self, src: int, dst: int) -> int:
        n = max(1, len(self.towns))
        if n <= 1:
            return 0
        a = (dst - src) % n
        b = (src - dst) % n
        d = a if a < b else b
        return max(1, int(d))

    def start_migration_pass(self) -> List[str]:
        logs: List[str] = []
        n = len(self.towns)
        if n <= 1:
            return logs

        for a in self.agents:
            if getattr(a, "traveling", False):
                continue

            poor = a.gold < 10.0
            isolated = len(a.friends) < 2
            in_debt = bool(a.debts_owed)
            pressured = poor and isolated
            p = 0.0
            if pressured:
                p += 0.015
            if in_debt and a.gold < 12.0:
                p += 0.010

            if self.rng.random() > p:
                continue

            choices = [t.town_id for t in self.towns if t.town_id != a.town_id]
            if not choices:
                continue

            dst = self.rng.choice(choices)
            eta = self.travel_distance(a.town_id, dst)

            a.traveling = True
            a.travel_src = a.town_id
            a.travel_dst = dst
            a.travel_eta = eta

            src_name = self.towns[a.travel_src].name
            dst_name = self.towns[a.travel_dst].name
            logs.append(f"{a.display()} left {src_name} for {dst_name} ({eta}d)")

        return logs

    def travel_tick_pass(self) -> List[str]:
        logs: List[str] = []
        for a in self.agents:
            if not getattr(a, "traveling", False):
                continue
            a.travel_eta -= 1
            if a.travel_eta > 0:
                continue

            a.traveling = False
            a.town_id = int(a.travel_dst)
            a.pos = (self.rng.randint(0, TOWN_W - 1), self.rng.randint(0, TOWN_H - 1))

            src_name = self.towns[int(a.travel_src)].name
            dst_name = self.towns[int(a.travel_dst)].name
            logs.append(f"{a.display()} arrived in {dst_name} from {src_name}")

        return logs


    # ── Tick loop ───────────────────────────────────────────────

    def tick(self) -> List[str]:
        logs: List[str] = []
        self.t += 1

        # move merchant along route
        self.merchant_town_id = (self.merchant_town_id + 1) % max(1, len(self.towns))

        # world background dynamics
        self.market.autoscale_for_population(len(self.agents))
        self.market.tick()
        self.town_stock_tick()

        # upkeep + goal issuance
        for a in self.agents:
            a.step_basic_needs()
            a.decay_reputation()
            a.decay_grudges()

        self.goal_issue_pass()


        # meetings + deadlines + overdue
        logs.extend(self.meeting_pass())
        logs.extend(self.goal_deadline_pass())
        logs.extend(self.debt_overdue_pass())
        logs.extend(self.travel_tick_pass())
        logs.extend(self.start_migration_pass())

        # random order
        order = self.agents[:]
        self.rng.shuffle(order)

        for a in order:
            if getattr(a, "traveling", False):
                continue
            event_work = self.work_and_maybe_sell(a)
            if event_work:
                logs.append(event_work)

            local = self.neighbors(a, radius=2)

            ev_in = self.market_buy_inputs_if_refiner(a)
            if ev_in:
                logs.append(ev_in)

            ev_goal = self.market_buy_goal_if_needed(a)
            if ev_goal:
                logs.append(ev_goal)

            ev_food = self.market_buy_food_if_needed(a)
            if ev_food:
                logs.append(ev_food)

            ev_sell = self.market_sell_excess(a)
            if ev_sell:
                logs.append(ev_sell)

            if local:
                repay = self.maybe_repay_local_debts(a, local)
                if repay:
                    logs.append(repay)

            if not local:
                continue

            did = False
            if a.wants_to_trade(self.rng):
                partner = self.rng.choice(local)
                ev_trade = self.trade(a, partner)
                if ev_trade:
                    logs.append(ev_trade)
                    did = True

            if not did and a.wants_to_talk(self.rng):
                partner = self.rng.choice(local)
                logs.append(self.talk(a, partner))
        self.update_social_classes()

        # drift trust back toward neutral over time
        for a in self.agents:
            for who, v in list(a.trust.items()):
                drift = 0.01
                if a.has_grudge(who, at_least=0.25):
                    drift = 0.025
                a.trust[who] = a.clamp01(v + (0.5 - v) * drift)

        return logs
    
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

# ╔══════════════════════════════════════════════════════════════╗
# ║ Setup helpers                                                ║
# ╚══════════════════════════════════════════════════════════════╝

def make_default_market(pop: int) -> Market:
    m = Market(
        stock={
            "food": 80,
            "wood": 60,
            "ore": 40,
            "stone": 50,
            "tools": 35,
            "cloth": 30,
            "charcoal": 12,
            "plank": 12,
            "ingot": 8,
        },
        target={"food": 65, "tools": 40, "luxury": 18},
        production={
            "food": 8,
            "wood": 4,
            "ore": 3,
            "stone": 3,
            "cloth": 3,
            "tools": 3,
        },
        demand={"food": 5, "tools": 1, "luxury": 1},
        price_sensitivity=MERCHANT_PRICE_SENS,
        spread=MERCHANT_SPREAD,
    )
    m.autoscale_for_population(pop)
    return m

def make_town_resources(rng: random.Random) -> set[str]:
    base = {"food", "wood", "ore", "stone", "tools", "cloth"}
    keep = set(base)
    for g in list(base):
        if g != "food" and rng.random() < TOWN_RESOURCE_MISS_CHANCE:
            keep.discard(g)
    keep.add("food")
    while len(keep) < TOWN_MIN_RESOURCES:
        keep.add(rng.choice(tuple(base)))
    return keep

def make_agents(rng: random.Random, n: int, *, town_id: int, town_resources: set[str]) -> List[Agent]:
    names = gen_unique_names(rng, n)
    rng.shuffle(names)

    # Jobs: producers only if town has the base resource; refiners always allowed (imports/expeditions can fill gaps).
    producer_jobs = [job for job, out in JOB_OUTPUT.items() if out in town_resources]
    jobs = producer_jobs + list(REFINE_RECIPES.keys())
    if not producer_jobs:
        jobs = ["farmer"] + list(REFINE_RECIPES.keys())

    agents: List[Agent] = []
    for i in range(n):
        home = (rng.randint(0, TOWN_W - 1), rng.randint(0, TOWN_H - 1))
        a = Agent(
            name=names[i],
            home=home,
            pos=home,
            honesty=rng.uniform(0.1, 0.95),
            greed=rng.uniform(0.1, 0.95),
            sociability=rng.uniform(0.2, 0.95),
            vengefulness=rng.uniform(0.1, 0.95),
            memory_depth=rng.randint(18, 55),
            town_id=town_id,
            native_town_id=town_id,
            job=rng.choice(jobs),
        )
        a.init_inv(rng)
        agents.append(a)

    # trust init only within the same town
    for a in agents:
        for b in agents:
            if a.name != b.name:
                a.ensure_trust(b.name)

    return agents

def make_world(rng: random.Random, total_pop: int) -> World:
    # town sizes sum to total_pop
    sizes: List[int] = []
    remaining = total_pop
    for i in range(NUM_TOWNS):
        if i == NUM_TOWNS - 1:
            sizes.append(max(TOWN_POP_MIN, remaining))
        else:
            lo = TOWN_POP_MIN
            hi = min(TOWN_POP_MAX, remaining - TOWN_POP_MIN * (NUM_TOWNS - i - 1))
            if hi < lo:
                hi = lo
            sz = rng.randint(lo, hi)
            sizes.append(sz)
        remaining -= sizes[-1]

    towns: List[Town] = []
    agents: List[Agent] = []
    for tid, pop in enumerate(sizes):
        resources = make_town_resources(rng)
        towns.append(Town(name=f"Town {tid+1}", town_id=tid, resources=resources))
        agents.extend(make_agents(rng, pop, town_id=tid, town_resources=resources))

    market = make_default_market(total_pop)
    world = World(agents=agents, towns=towns, rng=rng, market=market)
    # Start with merchant in town 0
    world.merchant_town_id = 0
    # initial goal pulse at t=0
    world.goal_issue_pass()
    return world

def make_multiverse(rng: random.Random, total_pop: int) -> MultiWorld:
    if NUM_REGIONS <= 1:
        return MultiWorld(regions=[make_world(rng, total_pop=total_pop)], active_region=0)

    pops: List[int] = [total_pop // NUM_REGIONS for _ in range(NUM_REGIONS)]
    for i in range(total_pop % NUM_REGIONS):
        pops[i] += 1

    regions: List[World] = []
    for rid, pop in enumerate(pops):
        # independent stream per region so they don't mirror each other too hard
        region_rng = random.Random(rng.randint(0, 2_000_000_000) + rid * 97)
        regions.append(make_world(region_rng, total_pop=pop))

    return MultiWorld(regions=regions, active_region=0)

# ╔══════════════════════════════════════════════════════════════╗
# ║ UI / CLI                                                     ║
# ╚══════════════════════════════════════════════════════════════╝

def run_ui(world: World, *, title: str = "Town Sim") -> None:
    try:
        from ui_screens import run_pygame_ui
    except Exception as e:
        raise SystemExit(
            "UI mode needs pygame + ui_screens.py in the same folder.\n"
            f"Import error: {e}"
        ) from e

    def step_once() -> list[str]:
        return world.tick()

    run_pygame_ui(world, step_once, title=title)

def headless_main(*, seed: int = SEED, n: int = NUM_AGENTS) -> None:
    rng = random.Random(seed)
    world = make_multiverse(rng, total_pop=n)

    print("\nTown sim start\n")
    for _ in range(TURNS):
        logs = world.tick()
        if logs:
            print(f"\n--- Turn {world.t} ---")
            for line in logs[:14]:
                print(line)
            if len(logs) > 14:
                print(f"... {len(logs) - 14} more events")
        if world.t % 10 == 0:
            mp_food = world.market.mid_price("food")
            print(f"\nMerchant in: {world.towns[world.merchant_town_id].name}  market_gold={world.market.gold:.2f}  food_mid={mp_food:.2f}")
    print("\nDone.")

def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("-n", type=int, default=NUM_AGENTS, help="number of agents")
    p.add_argument("--no-ui", action="store_true", help="run in terminal (headless)")
    p.add_argument("--ui", action="store_true", help="force UI (pygame)")
    args = p.parse_args()

    rng = random.Random(args.seed)
    world = make_multiverse(rng, total_pop=args.n)

    want_ui = args.ui or (not args.no_ui)
    if want_ui:
        try:
            run_ui(world)
            return
        except Exception as e:
            print("UI failed to start, falling back to headless.")
            print(f"Reason: {e}")
    headless_main(seed=args.seed, n=args.n)

if __name__ == "__main__":
    main()
