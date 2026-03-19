# Trade Sim

A multi-town gossip and trade society simulator where economies, reputations, and grudges emerge from individual agents doing their thing.

---

##  Overview
               ╱|、
              (˚ˎ。7  
               |、˜〵          
               じしˍ,)ノ

80 autonomous agents spread across 4 towns in 4 regions. Each one has a job, a personality, opinions about their neighbors, and goals they're trying to hit. There's one travelling Merchant Guild that physically moves town to town on a route — so if the merchant isn't in your town, you're stuck bartering with whoever's nearby.

Nobody is scripted to cooperate or betray anyone. What happens — alliances, scams, debt spirals, reputation warfare, mass migration — comes from the interaction of simple individual rules.

---

## How It Works  ₍^. .^₎⟆

| System | What It Does |
|--------|-------------|
| **Economy** | 21 goods across base resources and refined products. Refiners need inputs (ore → ingot → scimitar). Prices follow supply/demand with shortage multipliers. |
| **Merchant Guild** | A single global market that rotates between towns. Each town sees the merchant every N turns — miss it and you wait. |
| **Gossip & Rumors** | Agents spread rumors about people they hold grudges against. Confidence updates are Bayesian-ish — weighted by speaker trust and social status. Rumors mutate and exaggerate over hops. |
| **Reputation Tags** | RELIABLE, SCAMMER, UNRELIABLE — these decay over time, interact with each other (getting tagged SCAMMER suppresses RELIABLE), and affect trade offers and credit access. |
| **Credit & Debt** | Sellers can extend credit based on trust. Overdue debts trigger grudges, SCAMMER tags, and public rumor campaigns by the creditor. |
| **Goals** | Small/Medium/Big goals issued on timers. Agents buy, trade, and join expeditions to complete them. Success pays gold + reputation. Failure costs both. |
| **Expeditions** | Town meetings where agents pool gold to source missing resources from other towns. Investment is trust-gated — low-trust proposers get less funding. |
| **Migration** | Broke, isolated, or indebted agents sometimes leave town for a new start. They carry their reputation (and grudges) with them. |
| **Social Class** | Wealth percentile + job prestige + reputation tags → smoothed status score. Elites' gossip carries more weight. |

---

## Emergent Stuff

- Scammers get tagged, lose trade partners, and eventually starve or migrate
- Creditors who overextend credit end up spreading rumors about half the town  
- Expeditions fail when the proposer's trust is too low to attract funding
- Rumor chains mutate — "owes 4.2g" becomes "owes everyone money" after a few hops
- Towns with missing base resources depend entirely on expedition timing and merchant visits
- Occasionally an agent migrates, brings a grudge, and poisons a whole new social network

Every seed plays out differently.

---

## Running It

```bash
# with UI (pygame)
python town_sim.py

# headless
python town_sim.py --no-ui

# custom seed / population
python town_sim.py --seed 42 -n 120
```

Requires `pygame` for the UI. Falls back to terminal output if pygame isn't available.

---

## Structure

```
town_sim.py      # simulation engine (~2050 lines) — economy, agents, gossip, goals, expeditions
ui_screens.py    # pygame interface — town view, agent inspection, market prices
town_portal.py   # [WIP] head-tracked 3D portal visualization
```

---

## Future Ideas

- Cross-region trade caravans (inter-region merchant routes)
- Political structures (elected town leaders, taxation)
- Seasonal resource cycles
- Event log export for post-run analysis
- Language generation for agent names per-region (languagepy.py exists, just needs integration)
