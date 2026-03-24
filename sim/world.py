# sim/world.py
# the World: tick loop, trading, talking, gossip, goals, expeditions, travel
# cut from town_sim.py

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sim.config import (
    GOODS, BASE_VALUES, BASE_GOODS, COMMON_REFINED, RARE_REFINED,
    JOB_OUTPUT, BASE_OUTPUT_RANGE, REFINE_RECIPES, REFINE_OUTPUT_QTY,
    JOB_WAGE, TOWN_W, TOWN_H,
    DEBT_DUE_TURNS, CREDIT_MIN_DOWNPAY, CREDIT_MAX_FRACTION_OF_PRICE, CREDIT_MAX_ABS,
    DEBT_OVERDUE_TAG, OVERDUE_RUMOR_COOLDOWN, OVERDUE_RUMOR_REPOST_DELTA,
    MEETING_PROPOSE_EVERY, MEETING_HAPPENS_AFTER,
    goal_tier, edible_count,
)
from sim.types import MemoryEntry, Rumor, Goal, Debt
from sim.economy import Market
from sim.towns import Town, Meeting
from sim.agent import Agent
from sim.family import (
    FamilyUnit,
    aging_pass, marriage_pass, birth_pass,
    coming_of_age_pass, inheritance_pass, family_reputation_pass,
)


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
    families: Dict[int, FamilyUnit] = field(default_factory=dict)
    _name_rng: random.Random = field(default_factory=lambda: random.Random(999))

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

    # -- Goals ---------------------------------------------------

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

    # -- Town stock (for expeditions) ----------------------------

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

    # -- Work / trade / talk ------------------------------------

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

        # only negative claims here, since this is "grudge talk"
        claim = "is not reliable"
        if "scam" in tgt.reason:
            claim = "scams"
        if "debt" in tgt.reason or "owes" in tgt.reason:
            claim = "owes people money"

        # hide the grudge: sometimes it's subtle, sometimes it's spicy
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

    # -- Merchant market interactions ----------------------------

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

    # -- Debts --------------------------------------------------

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

    # -- Expeditions / meetings ----------------------------------

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
    
        # -- Travel / migration ------------------------------------

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


    # -- Tick loop -----------------------------------------------

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
            if not getattr(a, "alive", True):
                continue
            if a.job == "child":
                continue  # children eat from parents, handled below
            a.step_basic_needs()
            a.decay_reputation()
            a.decay_grudges()

        # feed children from parent inventory
        for a in self.agents:
            if not getattr(a, "alive", True):
                continue
            if a.job != "child":
                continue
            # find a living parent
            fed = False
            parents = getattr(a, "parents", None)
            if parents:
                for pname in parents:
                    for p in self.agents:
                        if p.name == pname and getattr(p, "alive", True):
                            food_key = "food"
                            for edible in ("food", "bread", "jerky", "ale"):
                                if p.inv.get(edible, 0) > 0:
                                    p.inv[edible] -= 1
                                    fed = True
                                    break
                            if fed:
                                break
                    if fed:
                        break
            # if no parent can feed, check family pool gold to buy food
            if not fed:
                a.months_starving = getattr(a, "months_starving", 0) + 1

        self.goal_issue_pass()

        # family lifecycle (every tick = 1 month)
        logs.extend(aging_pass(self.agents, self.families, self.t, self.rng))
        logs.extend(inheritance_pass(self.agents, self.families, self.t, self.rng))
        logs.extend(coming_of_age_pass(self.agents, self.families, self.towns, self.t, self.rng))
        logs.extend(marriage_pass(self.agents, self.families, self.t, self.rng))
        birth_logs, new_agents = birth_pass(self.agents, self.families, self.t, self.rng, self._name_rng)
        logs.extend(birth_logs)
        for child in new_agents:
            self.agents.append(child)
        family_reputation_pass(self.families, self.agents)


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
            if not getattr(a, "alive", True):
                continue
            if a.job == "child":
                continue
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
            if not getattr(a, "alive", True):
                continue
            for who, v in list(a.trust.items()):
                drift = 0.01
                if a.has_grudge(who, at_least=0.25):
                    drift = 0.025
                a.trust[who] = a.clamp01(v + (0.5 - v) * drift)

        return logs