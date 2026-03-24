# sim/family.py
# families, dynasties, lifecycle: birth, aging, marriage, death, inheritance
# agents now have lifespans, spouses, children, and belong to family units

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from sim.agent import Agent

from sim.config import (
    GOODS, JOB_OUTPUT, REFINE_RECIPES, TOWN_W, TOWN_H,
)
from sim.types import MemoryEntry
from sim.names import gen_unique_names


# ╔══════════════════════════════════════════════════════════════╗
# ║ Family config                                                ║
# ╚══════════════════════════════════════════════════════════════╝

# time scale: 1 tick = 1 month
CHILD_MATURITY_AGE = 192       # 16 years in months
ELDER_AGE = 660                # 55 years, decline starts
MAX_AGE = 960                  # 80 years hard cap
PREGNANCY_DURATION = 9         # 9 ticks = 9 months
COURTSHIP_MIN_AGE = 216        # 18 years
COURTSHIP_MIN_GOLD = 15.0
FERTILITY_PEAK = 0.05          # base chance per tick at peak age
FERTILITY_DECLINE_START = 360  # 30 years
MAX_CHILDREN = 5
INHERITANCE_GREED_THRESHOLD = 0.65  # greedy kids try to take extra
DEATH_STARVATION_THRESHOLD = 8     # months with no food before death risk


# ╔══════════════════════════════════════════════════════════════╗
# ║ FamilyUnit                                                   ║
# ╚══════════════════════════════════════════════════════════════╝

@dataclass
class FamilyUnit:
    family_id: int
    surname: str
    head: str                       # name of current family head
    members: set[str] = field(default_factory=set)
    deceased: List[str] = field(default_factory=list)
    wealth_pool: float = 0.0       # shared family savings
    reputation: float = 0.50       # family-level reputation 0..1
    alliances: Dict[int, float] = field(default_factory=dict)  # family_id -> strength
    feuds: Dict[int, float] = field(default_factory=dict)      # family_id -> intensity
    town_id: int = 0               # home town

    def living_count(self) -> int:
        return len(self.members)

    def add_member(self, name: str) -> None:
        self.members.add(name)

    def remove_member(self, name: str) -> None:
        self.members.discard(name)
        self.deceased.append(name)
        # if head dies, pick new head
        if name == self.head and self.members:
            self.head = next(iter(self.members))

    def contribute(self, amount: float) -> None:
        self.wealth_pool += max(0, amount)

    def withdraw(self, amount: float) -> float:
        take = min(amount, self.wealth_pool)
        self.wealth_pool -= take
        return take


# ╔══════════════════════════════════════════════════════════════╗
# ║ AgentLifeState (mixin fields for Agent)                      ║
# ╚══════════════════════════════════════════════════════════════╝

# these fields get added to the Agent dataclass directly
# listed here for documentation -- the actual fields are on Agent

# age: int = 0                    # in ticks (months)
# lifespan: int = 780             # genetic, ~65 years
# spouse: str | None = None
# children: list[str]
# parents: tuple[str, str] | None
# family_id: int = -1
# pregnant_with: str | None       # name of other parent
# pregnant_due: int = 0           # tick when child is born
# months_starving: int = 0        # consecutive months without food
# alive: bool = True
# cause_of_death: str | None = None


# ╔══════════════════════════════════════════════════════════════╗
# ║ Lifecycle helpers                                            ║
# ╚══════════════════════════════════════════════════════════════╝

def roll_lifespan(rng: random.Random, parent_a_lifespan: int = 780, parent_b_lifespan: int = 780) -> int:
    """genetic lifespan with parental influence and random variance"""
    base = (parent_a_lifespan + parent_b_lifespan) // 2
    variance = rng.randint(-60, 60)
    return max(480, min(MAX_AGE, base + variance))  # 40-80 years


def blend_trait(rng: random.Random, a: float, b: float, mutation: float = 0.08) -> float:
    """blend two parent traits with crossover and mutation"""
    weight = rng.uniform(0.35, 0.65)
    blended = a * weight + b * (1 - weight)
    blended += rng.uniform(-mutation, mutation)
    return max(0.05, min(0.95, blended))


def fertility_chance(age: int, base: float = FERTILITY_PEAK) -> float:
    """fertility decreases with age"""
    if age < COURTSHIP_MIN_AGE:
        return 0.0
    if age > FERTILITY_DECLINE_START:
        decline = (age - FERTILITY_DECLINE_START) / 300.0
        return max(0.0, base * (1.0 - decline))
    return base


def pick_child_job(rng: random.Random, parent_job: str, town_resources: set) -> str:
    """child likely follows parent trade, but might branch out"""
    # 50% chance to follow parent
    if rng.random() < 0.50:
        return parent_job

    # otherwise pick from available town jobs
    producer_jobs = [job for job, out in JOB_OUTPUT.items() if out in town_resources]
    all_jobs = producer_jobs + list(REFINE_RECIPES.keys())
    if not all_jobs:
        all_jobs = ["farmer"]
    return rng.choice(all_jobs)


# ╔══════════════════════════════════════════════════════════════╗
# ║ Lifecycle passes (called from World.tick)                    ║
# ╚══════════════════════════════════════════════════════════════╝

def aging_pass(agents: list, families: dict, t: int, rng: random.Random) -> List[str]:
    """age all agents, handle natural death and starvation"""
    logs: List[str] = []

    for a in agents:
        if not getattr(a, "alive", True):
            continue

        a.age += 1

        # starvation tracking -- children handled separately by parent feeding
        if a.job != "child":
            from sim.config import edible_count
            if edible_count(a.inv) <= 0:
                a.months_starving = getattr(a, "months_starving", 0) + 1
            else:
                a.months_starving = 0

        # death checks
        died = False
        cause = ""

        # old age
        if a.age >= a.lifespan:
            # increasing chance per month past lifespan
            overshoot = a.age - a.lifespan
            death_p = 0.05 + 0.03 * overshoot
            if rng.random() < death_p:
                died = True
                cause = "old age"

        # hard cap
        if a.age >= MAX_AGE:
            died = True
            cause = "old age"

        # starvation death
        if getattr(a, "months_starving", 0) >= DEATH_STARVATION_THRESHOLD:
            if rng.random() < 0.25:
                died = True
                cause = "starvation"

        if died:
            a.alive = False
            a.cause_of_death = cause
            logs.append(f"{a.display()} died ({cause}, age {a.age // 12}y)")
            a.remember(MemoryEntry(t, "death", a.name, a.name, f"Died: {cause}", 1.0))

            # handle family
            fam = families.get(getattr(a, "family_id", -1))
            if fam:
                fam.remove_member(a.name)

    return logs


def marriage_pass(agents: list, families: dict, t: int, rng: random.Random) -> List[str]:
    """pair up compatible unmarried agents"""
    logs: List[str] = []

    eligible = [
        a for a in agents
        if getattr(a, "alive", True)
        and getattr(a, "spouse", None) is None
        and getattr(a, "age", 0) >= COURTSHIP_MIN_AGE
        and a.gold >= COURTSHIP_MIN_GOLD
    ]

    # shuffle to avoid bias
    rng.shuffle(eligible)
    paired: set = set()

    for a in eligible:
        if a.name in paired:
            continue

        # find candidates: same town, opposite not already paired, compatible
        candidates = []
        for b in eligible:
            if b.name in paired or b.name == a.name:
                continue
            if b.town_id != a.town_id:
                continue
            # same family? skip (no incest)
            if getattr(a, "family_id", -1) == getattr(b, "family_id", -2) and getattr(a, "family_id", -1) >= 0:
                continue

            # compatibility: trust + sociability
            trust = a.trust.get(b.name, 0.5)
            if trust < 0.40:
                continue
            # check family feuds
            a_fam = families.get(getattr(a, "family_id", -1))
            b_fam = families.get(getattr(b, "family_id", -1))
            if a_fam and b_fam and b_fam.family_id in a_fam.feuds:
                if a_fam.feuds[b_fam.family_id] > 0.5:
                    continue  # feud too strong

            score = trust + 0.3 * a.sociability + 0.3 * b.sociability
            candidates.append((score, b))

        if not candidates:
            continue

        candidates.sort(key=lambda x: -x[0])
        # courtship probability
        best_score, partner = candidates[0]
        court_p = 0.02 * best_score * a.sociability
        if rng.random() > court_p:
            continue

        # marriage
        a.spouse = partner.name
        partner.spouse = a.name
        paired.add(a.name)
        paired.add(partner.name)

        # trust boost
        a.trust[partner.name] = min(1.0, a.trust.get(partner.name, 0.5) + 0.15)
        partner.trust[a.name] = min(1.0, partner.trust.get(a.name, 0.5) + 0.15)

        # family alliance
        a_fam = families.get(getattr(a, "family_id", -1))
        b_fam = families.get(getattr(b, "family_id", -1))
        if a_fam and b_fam and a_fam.family_id != b_fam.family_id:
            a_fam.alliances[b_fam.family_id] = a_fam.alliances.get(b_fam.family_id, 0.0) + 0.3
            b_fam.alliances[a_fam.family_id] = b_fam.alliances.get(a_fam.family_id, 0.0) + 0.3
            # marriage can reduce feuds
            if b_fam.family_id in a_fam.feuds:
                a_fam.feuds[b_fam.family_id] *= 0.7
            if a_fam.family_id in b_fam.feuds:
                b_fam.feuds[a_fam.family_id] *= 0.7

        a.remember(MemoryEntry(t, "marriage", a.name, partner.name, f"Married {partner.name}", 1.0))
        partner.remember(MemoryEntry(t, "marriage", partner.name, a.name, f"Married {a.name}", 1.0))
        logs.append(f"{a.display()} married {partner.display()}")

    return logs


def birth_pass(agents: list, families: dict, t: int, rng: random.Random, name_gen_rng: random.Random) -> Tuple[List[str], List]:
    """handle pregnancies and births, return (logs, new_agents)"""
    logs: List[str] = []
    new_agents = []

    for a in agents:
        if not getattr(a, "alive", True):
            continue
        if getattr(a, "spouse", None) is None:
            continue

        # check if already pregnant
        if getattr(a, "pregnant_with", None) is not None:
            if t >= getattr(a, "pregnant_due", 0):
                # give birth
                partner_name = a.pregnant_with
                partner = None
                for x in agents:
                    if x.name == partner_name:
                        partner = x
                        break

                # generate child
                child_name = gen_unique_names(name_gen_rng, 1)[0]
                # make sure name is unique
                existing = {x.name for x in agents}
                attempts = 0
                while child_name in existing and attempts < 100:
                    child_name = gen_unique_names(name_gen_rng, 1)[0]
                    attempts += 1

                from sim.agent import Agent

                # blend traits
                p_lifespan = a.lifespan if partner is None else partner.lifespan
                child_lifespan = roll_lifespan(rng, a.lifespan, p_lifespan)

                p_honesty = partner.honesty if partner else 0.5
                p_greed = partner.greed if partner else 0.5
                p_sociability = partner.sociability if partner else 0.5
                p_vengefulness = partner.vengefulness if partner else 0.5

                child = Agent(
                    name=child_name,
                    home=a.home,
                    pos=a.pos,
                    honesty=blend_trait(rng, a.honesty, p_honesty),
                    greed=blend_trait(rng, a.greed, p_greed),
                    sociability=blend_trait(rng, a.sociability, p_sociability),
                    vengefulness=blend_trait(rng, a.vengefulness, p_vengefulness),
                    memory_depth=rng.randint(18, 55),
                    town_id=a.town_id,
                    native_town_id=a.town_id,
                    job="child",   # not working yet
                    gold=0.0,
                    age=0,
                    lifespan=child_lifespan,
                    family_id=getattr(a, "family_id", -1),
                    parents=(a.name, partner_name),
                    alive=True,
                )
                child.inv = {g: 0 for g in GOODS}

                # register in family
                a.children.append(child_name)
                if partner:
                    partner.children.append(child_name)

                fam = families.get(getattr(a, "family_id", -1))
                if fam:
                    fam.add_member(child_name)

                a.pregnant_with = None
                a.pregnant_due = 0

                new_agents.append(child)
                logs.append(f"{a.display()} gave birth to {child_name}")
                a.remember(MemoryEntry(t, "birth", a.name, child_name, f"Gave birth to {child_name}", 1.0))
            continue

        # try to conceive
        if len(getattr(a, "children", [])) >= MAX_CHILDREN:
            continue

        chance = fertility_chance(a.age)
        if chance <= 0:
            continue

        # food security factor -- need decent food reserves to conceive
        from sim.config import edible_count
        food = edible_count(a.inv)
        if food < 4:
            chance *= 0.1   # almost no chance if food-insecure
        elif food < 8:
            chance *= 0.4

        if rng.random() < chance:
            a.pregnant_with = a.spouse
            a.pregnant_due = t + PREGNANCY_DURATION
            logs.append(f"{a.display()} is expecting (due t={a.pregnant_due})")

    return logs, new_agents


def coming_of_age_pass(agents: list, families: dict, towns: list, t: int, rng: random.Random) -> List[str]:
    """children who reach maturity get a job and starting gold"""
    logs: List[str] = []

    for a in agents:
        if not getattr(a, "alive", True):
            continue
        if a.job != "child":
            continue
        if a.age < CHILD_MATURITY_AGE:
            continue

        # pick a job
        town = towns[a.town_id] if a.town_id < len(towns) else None
        town_res = town.resources if town else {"food"}
        parent_job = "farmer"
        if getattr(a, "parents", None):
            for x in agents:
                if x.name == a.parents[0]:
                    parent_job = x.job if x.job != "child" else "farmer"
                    break

        a.job = pick_child_job(rng, parent_job, town_res)

        # starting gold from family
        fam = families.get(getattr(a, "family_id", -1))
        starter = 0.0
        if fam:
            starter = fam.withdraw(min(20.0, fam.wealth_pool * 0.15))
        a.gold = starter + rng.uniform(5.0, 15.0)

        # init inventory
        a.init_inv(rng)

        # init trust with town locals
        for b in agents:
            if b.town_id == a.town_id and b.name != a.name and getattr(b, "alive", True):
                a.ensure_trust(b.name)
                b.ensure_trust(a.name)

        logs.append(f"{a.display()} came of age, became {a.job}")
        a.remember(MemoryEntry(t, "coming_of_age", a.name, a.name, f"Became {a.job}", 1.0))

    return logs


def inheritance_pass(agents: list, families: dict, t: int, rng: random.Random) -> List[str]:
    """distribute wealth of the dead to their heirs"""
    logs: List[str] = []

    dead = [a for a in agents if not getattr(a, "alive", True) and a.gold > 0.1]

    for a in dead:
        estate = a.gold
        a.gold = 0.0

        # find heirs: children first, then spouse, then family pool
        living_children = []
        for child_name in getattr(a, "children", []):
            for x in agents:
                if x.name == child_name and getattr(x, "alive", True):
                    living_children.append(x)
                    break

        if living_children:
            # equal split, but greedy kids try to take extra
            base_share = estate / len(living_children)
            for child in living_children:
                share = base_share
                if child.greed > INHERITANCE_GREED_THRESHOLD and len(living_children) > 1:
                    # grab extra
                    grab = base_share * 0.3 * child.greed
                    share += grab
                    # siblings notice
                    for sib in living_children:
                        if sib.name != child.name:
                            sib.add_grudge(child.name, t=t, strength=0.4 * child.greed, reason="inheritance grab")
                child.gold += share
            logs.append(f"{a.name}'s estate ({estate:.1f}g) split among {len(living_children)} children")

        elif getattr(a, "spouse", None):
            spouse = None
            for x in agents:
                if x.name == a.spouse and getattr(x, "alive", True):
                    spouse = x
                    break
            if spouse:
                spouse.gold += estate
                logs.append(f"{a.name}'s estate ({estate:.1f}g) inherited by spouse {spouse.name}")
            else:
                fam = families.get(getattr(a, "family_id", -1))
                if fam:
                    fam.contribute(estate)
                    logs.append(f"{a.name}'s estate ({estate:.1f}g) returned to family pool")
        else:
            fam = families.get(getattr(a, "family_id", -1))
            if fam:
                fam.contribute(estate)

    return logs


def family_reputation_pass(families: dict, agents: list) -> None:
    """update family reputation based on living members"""
    for fam in families.values():
        if fam.living_count() == 0:
            continue
        total_status = 0.0
        count = 0
        for name in fam.members:
            for a in agents:
                if a.name == name and getattr(a, "alive", True):
                    total_status += a.status
                    count += 1
                    break
        if count > 0:
            target = total_status / count
            fam.reputation = 0.9 * fam.reputation + 0.1 * target

        # decay feuds and alliances slowly
        for fid in list(fam.feuds.keys()):
            fam.feuds[fid] *= 0.995
            if fam.feuds[fid] < 0.05:
                del fam.feuds[fid]
        for fid in list(fam.alliances.keys()):
            fam.alliances[fid] *= 0.998
            if fam.alliances[fid] < 0.05:
                del fam.alliances[fid]