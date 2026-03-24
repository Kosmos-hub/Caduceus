# sim/config.py
# all constants, goods, jobs, recipes, goal tiers
# cut from town_sim.py -- the single source of truth for tuning knobs

from __future__ import annotations

from typing import Dict


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
JOB_WAGE = 18

# Merchant Guild: one global market that physically moves town-to-town.
# Each turn it is in exactly one town (route is town0 -> town1 -> ... -> townN-1 -> town0).
# So each town sees the merchant every NUM_TOWNS turns.
MERCHANT_SPREAD = 0.14
MERCHANT_PRICE_SENS = 0.85

# Expeditions / meetings
MEETING_PROPOSE_EVERY = 6
MEETING_HAPPENS_AFTER = 1
MEETING_MIN_FUND = 40.0

# Credit / debt
DEBT_DUE_TURNS = 24
CREDIT_MIN_DOWNPAY = 0.75
CREDIT_MAX_FRACTION_OF_PRICE = 0.70
CREDIT_MAX_ABS = 40.0

# Reputation
TAG_DECAY = 0.97
DEBT_OVERDUE_TAG = 0.65
OVERDUE_RUMOR_COOLDOWN = 4
OVERDUE_RUMOR_REPOST_DELTA = 2.0

# grudges (only spread negative rumors / betray when wronged)
GRUDGE_DECAY = 0.985
GRUDGE_MIN_KEEP = 0.12
GRUDGE_MAX = 1.0

# starvation
STARVE_GOLD_PENALTY = 3.0

# market scaling
MARKET_GOLD_START = 2000.0
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
    "farmer": (6, 12),
    "lumberjack": (6, 10),
    "miner": (4, 8),
    "mason": (4, 8),
    "weaver": (4, 8),
    "crafter": (3, 6),
}

REFINE_RECIPES = {
    # Food
    "baker": ("bread", {"food": 3}),
    "brewer": ("ale", {"food": 3}),
    "butcher": ("jerky", {"food": 3}),
    # Wood
    "sawyer": ("plank", {"wood": 3}),
    "kilnworker": ("charcoal", {"wood": 3}),
    "carpenter": ("furniture", {"plank": 2}),
    # Ore
    "smelter": ("ingot", {"ore": 3}),
    "metalsmith": ("scimitar", {"ingot": 2}),
    "jeweler": ("ring", {"ingot": 2}),
    # Stone
    "brickmaker": ("brick", {"stone": 3}),
    "sculptor": ("sculpture", {"stone": 2}),
    # Cloth
    "tailor": ("garment", {"cloth": 2}),
    "dyer": ("banner", {"cloth": 2}),
    # Tools
    "wheelwright": ("wagon", {"tools": 2}),
    "locksmith": ("lockbox", {"tools": 2}),
}

REFINE_OUTPUT_QTY = {
    "baker": 6,
    "brewer": 5,
    "butcher": 5,
    "sawyer": 6,
    "kilnworker": 5,
    "carpenter": 3,
    "smelter": 5,
    "metalsmith": 2,
    "jeweler": 2,
    "brickmaker": 6,
    "sculptor": 2,
    "tailor": 4,
    "dyer": 3,
    "wheelwright": 2,
    "locksmith": 2,
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