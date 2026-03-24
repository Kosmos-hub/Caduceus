# Town Sim v2 — Architecture & Revamp Plan

---

## 1. Language Decision: Stay Python, Architect for Future C

**Verdict: Python now. C later if needed. Here's why.**

The bottleneck right now isn't CPU — it's missing systems. Families, politics, buildings, warfare — each of these is weeks of design iteration where you'll be changing data structures and logic constantly. Python lets you do that 5x faster than C++.

The actual performance math:
- 80 agents: Python handles this trivially, even with O(n²) neighbor scans
- 500 agents: Still fine with basic optimization (spatial hashing for neighbors, NumPy for bulk trust decay)
- 2000+ agents: This is where Python starts sweating. But you're months away from needing this.

**The escape hatch:** Structure the sim as a pure-logic library with zero UI imports. Every struct is a plain dataclass. Every method takes explicit state and returns explicit results. When the day comes to port the tick loop to C, you're porting a clean state machine — not untangling spaghetti.

**Framework shift for the UI:** Pygame is going to choke on the dashboard + tile map + graphs vision. Two paths:

| Option | Pros | Cons |
|--------|------|------|
| **Pygame + pygame_gui** | You already know it, stays native | No real chart library, tile map rendering is manual, UI widgets are primitive |
| **Python sim + web frontend** | Real charts (Chart.js/D3), real UI components, tile map via canvas/pixi.js, looks professional | Needs a bridge (Flask-SocketIO or similar), two codebases |

**Recommendation:** Python sim backend + web frontend via Flask-SocketIO. The dashboard/charts/graphs you want basically already exist as JavaScript libraries. The tile map is a canvas element. The sim pushes state to the browser every tick. This also means you could eventually run it headless on your server and view it from any device on your tailnet.

---

## 2. Project Structure

```
town_sim_v2/
├── sim/                        # pure simulation, zero UI
│   ├── __init__.py
│   ├── config.py               # all constants, tuning knobs
│   ├── types.py                # core dataclasses (Agent, Town, Family, Faction, Building...)
│   ├── names.py                # name generation (Tuareg-inspired)
│   ├── economy.py              # market, trading, crafting, taxation, buildings
│   ├── social.py               # trust, rumors, gossip, reputation, grudges
│   ├── family.py               # marriage, children, inheritance, dynasties
│   ├── politics.py             # factions, elections, laws, council, corruption
│   ├── military.py             # militia, raids, defense, territorial control
│   ├── goals.py                # personal goals, ambitions, needs hierarchy
│   ├── world.py                # World + MultiWorld, tick orchestration
│   └── setup.py                # world generation, agent spawning
│
├── ui/                         # web frontend
│   ├── server.py               # Flask-SocketIO bridge
│   ├── static/
│   │   ├── app.js              # main client logic
│   │   ├── dashboard.js        # charts, graphs, data panels
│   │   ├── tilemap.js          # pixel/tile map renderer (canvas)
│   │   ├── network.js          # social network force graph (d3)
│   │   └── style.css
│   └── templates/
│       └── index.html
│
├── main.py                     # entry point
└── requirements.txt
```

---

## 3. New Simulation Systems (Priority Order)

### 3.1 Families & Dynasties (Priority 1)

This is the big one. Right now agents are isolated individuals who pop into existence and never die. Families give the simulation continuity, stakes, and emergent stories.

**Core data:**

```python
@dataclass
class FamilyUnit:
    family_id: int
    surname: str                    # inherited, Tuareg-style matrilineal option
    head: str                       # agent name of current patriarch/matriarch
    members: set[str]               # living members
    deceased: list[str]             # dead members (for lineage tracking)
    wealth_pool: float              # shared family savings
    reputation: float               # family-level reputation (0..1)
    alliances: dict[int, float]     # family_id -> alliance strength
    feuds: dict[int, float]         # family_id -> feud intensity
    homestead_id: int | None        # primary building

@dataclass
class AgentLifeState:
    age: int                        # in turns (1 turn = ~1 week? 1 month?)
    lifespan: int                   # genetic + random
    spouse: str | None
    children: list[str]
    parents: tuple[str, str] | None
    family_id: int
    fertility: float                # decreases with age
    cause_of_death: str | None
```

**Lifecycle events:**
- **Birth:** Child inherits blended traits from parents + random mutation. Gets family surname. Starts as dependent (no job, consumes family resources).
- **Coming of age:** (~16 turns?) Agent picks a job based on family trade, town needs, or personal traits. Gets initial gold from family wealth pool.
- **Courtship:** Agents with high sociability + compatible traits + sufficient gold seek partners. Cross-family marriage creates alliances. Trust between families matters — you won't marry into a SCAMMER family.
- **Marriage:** Merges households or one partner moves. Combined wealth. Shared reputation effects.
- **Children:** Probabilistic based on fertility, age, food security. 1-4 children typical. Each child is a new Agent with blended genetics.
- **Death:** Natural (age), starvation, (later: combat). Inheritance splits wealth among children. If no children, goes to spouse, then family pool, then dissipates.
- **Inheritance disputes:** If multiple children, the greediest may try to take more than their share — generating grudges between siblings.

**Dynasty tracking:**
- Family tree stored as a directed graph (parent -> child edges)
- "Great families" emerge naturally: families that maintain wealth and reputation across generations
- Family feuds persist across generations (Romeo & Juliet dynamics)
- Intermarriage between feuding families can resolve OR intensify conflicts

**Time scale adjustment:**
Currently 1 tick = 1 day (agents eat food each tick). For dynasties to work, you probably want 1 tick = 1 week or 1 month. This means:
- Food consumption scales down (1 food/tick = 1 food/week)
- Agent lifespan = ~600-800 ticks (50-65 years at 1 tick/month)
- Children mature in ~192 ticks (16 years)
- Pregnancy = 9 ticks (months)

This is a fundamental rebalance. Everything in the economy needs to scale with it.

---

### 3.2 Politics & Factions (Priority 2)

Right now social dynamics are purely interpersonal. Politics adds collective decision-making, power structures, and factional conflict.

**Core data:**

```python
@dataclass
class Faction:
    faction_id: int
    name: str                       # "Merchant Guild", "Miners' Union", "Old Families"
    ideology: dict[str, float]      # e.g. {"trade_tax": 0.8, "immigration": 0.3, "military": 0.6}
    leader: str                     # agent name
    members: set[str]
    influence: float                # 0..1, affects law votes
    treasury: float
    allied_factions: set[int]
    rival_factions: set[int]

@dataclass
class Law:
    law_id: int
    name: str                       # "Trade Tax", "Immigration Ban", "Conscription"
    effect: dict[str, float]        # what it changes in the sim
    proposed_by: int                # faction_id
    votes_for: int
    votes_against: int
    enacted: bool
    enacted_t: int | None

@dataclass
class TownCouncil:
    town_id: int
    seats: int                      # 3-7 depending on town size
    council_members: list[str]      # agent names
    active_laws: list[Law]
    election_interval: int          # turns between elections
    next_election_t: int
    corruption_level: float         # 0..1, affects tax skimming
```

**Political mechanics:**
- **Faction formation:** Factions form around shared interests. Miners want low taxes on ore. Merchants want free trade. Old families want to keep power. Agents join factions based on job, wealth, family ties, and ideology alignment.
- **Elections:** Each town has a council. Every N turns, elections happen. Agents vote based on: faction loyalty > family loyalty > personal trust in candidates > ideology match. Wealthy agents and faction leaders can "campaign" (spend gold to influence votes).
- **Laws:** Council passes laws that affect the sim. A trade tax takes a % of all market transactions. An immigration ban prevents migration into the town. Conscription forces able-bodied agents into militia.
- **Corruption:** Council members with high greed skim from town treasury. If caught (rumor spreads), scandal reduces their reputation and faction influence.
- **Inter-town politics:** Towns can form trade agreements, declare embargoes, or (later) declare war. This requires a regional council or diplomacy system.

**Faction ideology dimensions:**
- `trade_openness`: free trade vs. protectionism
- `tax_rate`: low vs. high taxation
- `military_priority`: peaceful vs. militaristic
- `tradition`: conservative (old families) vs. progressive (newcomers)
- `immigration`: open borders vs. closed

Agents have personal ideology vectors too. Faction membership shifts ideology over time (echo chambers). Major events (famine, war, scam scandal) can cause ideology shifts.

---

### 3.3 Deeper Economy: Buildings, Supply Chains, Taxation (Priority 3)

The current economy is agent-inventory-only. Buildings add persistent infrastructure, investment, and a reason to care about towns long-term.

**Buildings:**

```python
@dataclass
class Building:
    building_id: int
    kind: str                       # "farm", "mine", "workshop", "market_stall", "tavern", "wall", "barracks"
    town_id: int
    owner: str                      # agent name (or family_id?)
    workers: list[str]              # agents employed here
    max_workers: int
    level: int                      # upgrade level (1-3)
    durability: float               # degrades over time, needs repair
    production_bonus: float         # multiplier on output
    construction_cost: dict[str, int]   # goods required to build
    upkeep_cost: dict[str, int]     # goods consumed per tick to maintain
    built_t: int
```

**Building types:**

| Building | Function | Workers | Output |
|----------|----------|---------|--------|
| Farm | Produces food | 1-4 | +50% food per worker vs. solo farming |
| Mine | Produces ore | 1-3 | +50% ore, unlocks deep ore at level 2 |
| Sawmill | Produces wood/plank | 1-3 | +40% wood output |
| Workshop | Refining station | 1-2 | +30% refining output, can handle 2 recipes |
| Market Stall | Local trading post | 1 | Allows P2P trading without proximity requirement |
| Tavern | Social hub | 1 | +gossip spread range, +faction recruitment, generates small income |
| Granary | Food storage | 0 | Prevents food spoilage for the town, emergency reserve |
| Wall | Defense | 0 | +defense rating for the town |
| Barracks | Military | 1-2 | Trains militia, stores weapons |

**Supply chains get deeper:**
```
ore -> smelter -> ingot -> metalsmith -> scimitar
                        -> jeweler -> ring
                        -> toolmaker -> advanced_tools

wood -> sawyer -> plank -> carpenter -> furniture
                       -> shipwright -> boat (enables fishing, trade routes)

food -> baker -> bread
     -> brewer -> ale (tavern input)
     -> butcher -> jerky (travel rations)

cloth -> tailor -> garment
      -> tentmaker -> tent (expedition gear)
```

**Taxation:**
- Town council sets a tax rate (0-25%)
- Tax collected on: market transactions, building income, expedition profits
- Tax goes to town treasury
- Treasury funds: wall repairs, road building, militia wages, expedition subsidies
- Corrupt council members skim (proportional to their greed × corruption_level)

**Employment system:**
- Instead of every agent being a solo producer, agents can work at buildings
- Building owner pays wages, keeps profit margin
- Workers earn steady income but don't own output
- Creates natural class division: building owners (bourgeoisie) vs. workers (proletariat)
- Feeds directly into faction politics

---

### 3.4 Military & Warfare (Priority 4)

Last priority but still important for stakes. Without military, there's no real consequence to inter-town conflict.

**Core data:**

```python
@dataclass
class MilitiaUnit:
    unit_id: int
    town_id: int
    soldiers: list[str]             # agent names
    equipment: dict[str, int]       # "scimitar": 3, "banner": 1
    morale: float
    training: float                 # 0..1, improves over time in barracks
    deployed: bool
    target_town: int | None

@dataclass
class Raid:
    attacker_town: int
    defender_town: int
    attacker_units: list[int]       # unit_ids
    defender_units: list[int]
    started_t: int
    resolved: bool
    loot: dict[str, int]            # goods taken
    casualties_atk: list[str]       # agent names killed
    casualties_def: list[str]
```

**Military mechanics:**
- **Militia:** Towns can recruit agents into militia (voluntary or conscription via law). Militia needs equipment (scimitars, banners for morale).
- **Training:** Militia in barracks slowly improves training level. Untrained militia is barely effective.
- **Raids:** A faction or council can vote to raid another town. Militia travels (like migration), fights, and either loots or is repelled.
- **Combat resolution:** Simple stat comparison: (soldiers × training × equipment × morale) vs. (defenders × training × walls × morale). Probabilistic casualties on both sides.
- **Consequences:** Looted towns lose goods from local_stock and building durability. Raiders bring loot home. Dead agents trigger family grudges and faction retaliation.
- **Deterrence:** Strong walls + large militia = nobody raids you. Weak towns get picked on. Arms races emerge.

---

## 4. UI Architecture: Dashboard + Tile Map

### 4.1 Technology Stack

```
Python (sim) <--Flask-SocketIO--> Browser (dashboard + tile map)
```

- **Backend:** Flask-SocketIO pushes sim state to browser every tick
- **Frontend:** Vanilla JS + Chart.js (graphs) + Canvas API (tile map) + D3.js (social network)
- **Communication:** WebSocket events: `tick_update`, `agent_detail`, `town_detail`, `map_state`

### 4.2 Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ [▶ Play] [⏸] [1x] [2x] [5x] [10x]    Turn: 847    Region 1/4     │
│ ┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐       │
│ │ Overview  ││ Economy  ││ People   ││ Politics ││ Military │ [MAP] │
│ └──────────┘└──────────┘└──────────┘└──────────┘└──────────┘       │
├────────────────────────────────┬────────────────────────────────────┤
│                                │                                    │
│   LEFT PANEL                   │   RIGHT PANEL                      │
│   (context-dependent)          │   (context-dependent)              │
│                                │                                    │
│   - Agent list (sortable)      │   - Detail view for selected item  │
│   - Town selector              │   - Charts & graphs                │
│   - Family tree viewer         │   - Social network graph           │
│   - Faction roster             │   - Event log with filters         │
│                                │                                    │
├────────────────────────────────┴────────────────────────────────────┤
│ EVENT TICKER (scrolling log of recent events, filterable)           │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.3 Tab Breakdown

**Overview tab:**
- Town summary cards (population, wealth, resources, merchant ETA)
- Global economy sparklines (food price, total gold, trade volume over time)
- Population pyramid (age distribution once families exist)
- "Headlines" — most dramatic recent events (scams, deaths, elections, raids)

**Economy tab:**
- LEFT: Market price table (current), building list for selected town
- RIGHT TOP: Line chart — price history for selected goods (Chart.js)
- RIGHT MID: Bar chart — town wealth comparison, Gini coefficient over time
- RIGHT BOTTOM: Sankey or flow diagram — trade flows between towns

**People tab:**
- LEFT: Sortable agent table (name, job, gold, status, family, faction)
- RIGHT: Agent detail panel (same as current Agent tab but richer)
  - Profile: stats, inventory, goals, family, faction membership
  - Brain: opinions, grudges, memories, rumors known
  - Family: family tree (interactive d3 tree layout)
  - History: personal event timeline

**Politics tab:**
- LEFT: Faction list with member counts, influence bars
- RIGHT: Council view for selected town — members, active laws, upcoming election
- Charts: faction influence over time, ideology scatter plot, corruption index

**Military tab:**
- LEFT: Militia rosters by town, equipment status
- RIGHT: Active raids, defense ratings, casualty reports
- Chart: military strength comparison between towns

### 4.4 Tile Map (MAP button)

Clicking MAP opens a full-screen canvas overlay — the Songs of Syx-style view.

**Map structure:**
```
REGION MAP (zoomed out)          TOWN MAP (zoomed in)
┌───────────────────────┐       ┌───────────────────────┐
│                       │       │ ♟♟  🏠🏠  ⛏        │
│   [Town 1]---[Town 2] │       │ ♟   🏠   🌾🌾🌾    │
│      |    \    |      │  -->  │     🍺   🌾🌾       │
│   [Town 3]---[Town 4] │       │ ♟♟  🏗   ⬜⬜       │
│                       │       │          🏪 🧱🧱     │
└───────────────────────┘       └───────────────────────┘
```

**Region map:** Shows towns as nodes with connecting roads. Road thickness = trade volume. Town size = population. Color = dominant faction. Merchant guild shown as a moving sprite on the road. Agents in transit shown as dots on roads.

**Town map (click to zoom):** Tile grid matching TOWN_W × TOWN_H. Each tile can contain: agents (as colored dots), buildings (as pixel sprites), resources. Agent color = social class (poor=gray, common=white, comfortable=blue, elite=gold). Buildings are distinct sprites per type.

**Implementation:** HTML5 Canvas with a camera system (pan + zoom). Tile sprites are 16x16 or 32x32 pixel art. Agent dots are simple circles. Buildings are pre-drawn sprite sheets.

---

## 5. AI Upgrades

The current agent AI is reactive — they respond to immediate needs (hungry? buy food. have grudge? spread rumors). V2 agents should have layered decision-making:

### 5.1 Needs Hierarchy (Maslow-ish)

```
SURVIVAL:   food, shelter (building)
SECURITY:   gold reserve, debt-free, safe town
SOCIAL:     friends, family bonds, faction belonging
STATUS:     reputation, social class, political power
LEGACY:     children's success, family wealth, dynasty prestige
```

Each tick, agents evaluate needs from bottom to top. They only pursue higher needs when lower ones are satisfied. A starving elite will sell their building before they die.

### 5.2 Planning

Instead of purely reactive decisions, agents maintain a short-term plan:

```python
@dataclass
class AgentPlan:
    priority: str                   # "feed_family", "build_workshop", "run_for_council"
    steps: list[str]                # ["buy wood x10", "buy stone x5", "hire builder"]
    progress: int                   # which step we're on
    deadline: int                   # give up if not done by this turn
    fallback: str | None            # what to do if plan fails
```

Plans are generated from the needs hierarchy. An agent who wants to move from "common" to "comfortable" might plan: save 200 gold -> build a workshop -> hire workers -> increase income.

### 5.3 Social Intelligence

- **Strategic gossip:** Instead of randomly sharing rumors, agents consider: "Will spreading this rumor help me? Hurt my enemy? Strengthen my faction?"
- **Alliance building:** Agents actively seek to befriend useful people (rich, powerful, well-connected) — weighted by sociability and greed.
- **Betrayal calculus:** Before scamming, agents evaluate: risk of getting caught × reputation damage × grudge retaliation vs. immediate gold gain.

---

## 6. Data & Graphs Wishlist

Time series to track and chart:

| Metric | Chart Type | Update Frequency |
|--------|-----------|-----------------|
| Good prices (per good) | Line chart (multi-series) | Every tick |
| Total gold in circulation | Line chart | Every tick |
| Population by town | Stacked area chart | Every tick |
| Trade volume (by good, by town pair) | Heatmap or Sankey | Every 10 ticks |
| Gini coefficient (wealth inequality) | Line chart | Every 10 ticks |
| Social class distribution | Stacked bar | Every 10 ticks |
| Faction influence | Stacked area | Every tick |
| Family wealth (top 5 families) | Line chart (multi-series) | Every 10 ticks |
| Rumor propagation | Network animation (d3) | On event |
| Agent lifespan distribution | Histogram | On death |
| Food security index by town | Line chart | Every tick |
| Building count by type by town | Grouped bar | Every 25 ticks |
| Election results history | Bar chart | On election |
| Raid outcomes | Timeline | On resolution |

---

## 7. Implementation Phases

### Phase 0: Refactor (1-2 sessions)
- Split town_sim.py into the `sim/` module structure
- Extract all constants into config.py
- Make World a pure state machine (no UI, no pygame imports)
- Add time series recording (list of snapshots for charts)
- Unit tests for core mechanics

### Phase 1: Web UI Shell (2-3 sessions)
- Flask-SocketIO server pushing tick state
- Basic dashboard with tabs (Overview, Economy, People)
- Agent list + detail panel (port existing pygame functionality)
- Market price table + first Chart.js line chart (price history)
- Speed controls, pause, town selector

### Phase 2: Families (3-4 sessions)
- Time scale adjustment (1 tick = 1 month?)
- AgentLifeState, FamilyUnit dataclasses
- Birth, aging, death, marriage, inheritance
- Family tree visualization (d3 tree)
- Rebalance economy for new time scale

### Phase 3: Tile Map (2-3 sessions)
- Canvas-based region map (town nodes + roads)
- Town zoom view (tile grid with agents + buildings)
- Merchant guild animation on roads
- Click-to-select agents on map -> opens detail panel

### Phase 4: Buildings & Employment (2-3 sessions)
- Building construction system
- Employment (workers at buildings)
- Building production bonuses
- Building sprites on tile map
- Taxation system (simple flat tax)

### Phase 5: Politics (2-3 sessions)
- Factions (auto-formed from shared interests)
- Town councils + elections
- Law system (trade tax, immigration, conscription)
- Corruption mechanics
- Politics tab in dashboard

### Phase 6: Military (2 sessions)
- Militia recruitment + training
- Raid system (travel, combat resolution, looting)
- Walls + barracks buildings
- Military tab in dashboard

### Phase 7: Polish (ongoing)
- More charts and data views
- Social network force graph (d3)
- Notification system for dramatic events
- Save/load game state (JSON serialization)
- Performance optimization if needed

---

## 8. Key Design Principles

1. **Sim is a library.** Zero imports from UI code. You should be able to `from sim.world import World; w.tick()` in a Python REPL and everything works.

2. **State is serializable.** Every dataclass should be JSON-round-trippable. This enables save/load, replay, and debugging.

3. **Events are structured.** No more string parsing for event data. Every event is a typed dataclass with metadata. The UI can filter, search, and visualize events without regex.

4. **Time series are first-class.** The sim records snapshots every N ticks into a history buffer. Charts read from this buffer. No reconstructing history from logs.

5. **Emergent over scripted.** No hardcoded storylines. Every dramatic event (family feud, political scandal, economic crash) should emerge from agent decisions interacting with system mechanics.
