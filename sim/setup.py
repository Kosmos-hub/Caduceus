# sim/setup.py
# world generation: markets, towns, agents, multiverse
# cut from town_sim.py

from __future__ import annotations

import random
from typing import List

from sim.config import (
    GOODS, BASE_GOODS, JOB_OUTPUT, REFINE_RECIPES,
    TOWN_W, TOWN_H, NUM_TOWNS, NUM_REGIONS,
    TOWN_POP_MIN, TOWN_POP_MAX,
    TOWN_RESOURCE_MISS_CHANCE, TOWN_MIN_RESOURCES,
    MERCHANT_PRICE_SENS, MERCHANT_SPREAD,
)
from sim.economy import Market
from sim.towns import Town
from sim.agent import Agent
from sim.names import gen_unique_names
from sim.world import World
from sim.regions import MultiWorld
from sim.family import FamilyUnit


# ╔══════════════════════════════════════════════════════════════╗
# ║ Setup helpers                                                ║
# ╚══════════════════════════════════════════════════════════════╝

def make_default_market(pop: int) -> Market:
    m = Market(
        stock={
            "food": 300,
            "wood": 200,
            "ore": 150,
            "stone": 180,
            "tools": 120,
            "cloth": 100,
            "charcoal": 40,
            "plank": 50,
            "ingot": 30,
        },
        target={"food": 250, "tools": 120, "luxury": 40},
        production={
            "food": 30,
            "wood": 15,
            "ore": 12,
            "stone": 12,
            "cloth": 12,
            "tools": 10,
        },
        demand={"food": 20, "tools": 4, "luxury": 2},
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
            age=rng.randint(216, 480),    # 18-40 years old, founding generation
            lifespan=rng.randint(660, 840),  # 55-70 years
        )
        a.init_inv(rng)
        agents.append(a)

    # trust init only within the same town
    for a in agents:
        for b in agents:
            if a.name != b.name:
                a.ensure_trust(b.name)

    return agents


def make_families(rng: random.Random, agents: List[Agent], town_id: int) -> dict[int, FamilyUnit]:
    """group agents into initial families (~3-5 per family) and pair some as married"""
    families: dict[int, FamilyUnit] = {}
    surnames = gen_unique_names(rng, len(agents) // 3 + 2)

    # shuffle agents and group them
    town_agents = [a for a in agents if a.town_id == town_id]
    rng.shuffle(town_agents)

    fam_id_counter = town_id * 1000  # namespace family IDs by town
    idx = 0
    while idx < len(town_agents):
        size = rng.randint(2, 5)
        group = town_agents[idx:idx + size]
        idx += size

        surname = surnames[len(families) % len(surnames)]
        fam = FamilyUnit(
            family_id=fam_id_counter,
            surname=surname,
            head=group[0].name,
            town_id=town_id,
        )

        for a in group:
            a.family_id = fam_id_counter
            fam.add_member(a.name)

        # pair first two as married if both old enough
        if len(group) >= 2:
            a, b = group[0], group[1]
            if a.age >= 216 and b.age >= 216:
                a.spouse = b.name
                b.spouse = a.name
                # give them 1-2 "children" (other family members)
                for child in group[2:]:
                    child.parents = (a.name, b.name)
                    a.children.append(child.name)
                    b.children.append(child.name)
                    # children are younger
                    child_max_age = max(216, min(a.age - 192, 360))
                    child.age = rng.randint(216, child_max_age)

        families[fam_id_counter] = fam
        fam_id_counter += 1

    return families

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

    # generate initial families per town
    all_families: dict[int, FamilyUnit] = {}
    for tid in range(len(towns)):
        town_fams = make_families(rng, agents, tid)
        all_families.update(town_fams)
    world.families = all_families

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