# ui/server.py
# web UI server -- decoupled sim loop, throttled visual updates
# sim runs as fast as it can, UI gets snapshots at ~12fps max

from __future__ import annotations

import sys, os, time, threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO, emit

from sim.config import SEED, NUM_AGENTS, edible_count
from sim.setup import make_multiverse
import random


app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = "townsim"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── sim state ──────────────────────────────────────────────────

rng = random.Random(SEED)
world = make_multiverse(rng, total_pop=NUM_AGENTS)

sim_lock = threading.Lock()
sim_running = False
sim_speed = 1.0
UI_FPS = 12
MIN_FRAME_DT = 1.0 / UI_FPS

# snapshot cache -- only rebuild when turn changes
_snap_cache = None
_snap_turn = -1

# event buffers
_events_buffer: list[dict] = []     # pending for next UI push
_events_all: list[dict] = []        # full ring buffer
MAX_EVENTS = 2000


def snapshot() -> dict:
    """cached snapshot -- free on repeated reads within same turn"""
    global _snap_cache, _snap_turn
    w = world.current() if hasattr(world, "current") else world
    if _snap_turn == w.t and _snap_cache is not None:
        return _snap_cache

    town_pops = [0] * len(w.towns)
    for a in w.agents:
        if 0 <= a.town_id < len(town_pops):
            town_pops[a.town_id] += 1

    towns_data = [{
        "name": t.name,
        "town_id": t.town_id,
        "resources": sorted(list(t.resources)),
        "local_stock": {g: t.local_stock.get(g, 0) for g in ("food", "wood", "ore", "stone", "tools", "cloth")},
        "pop": town_pops[t.town_id],
    } for t in w.towns]

    # lightweight agent data -- no inventory, no goals, no social graph
    agents_data = [{
        "name": a.name,
        "job": a.job,
        "gold": round(a.gold, 2),
        "town_id": a.town_id,
        "status": round(a.status, 3),
        "social_class": a.social_class,
        "food": edible_count(a.inv),
        "traveling": getattr(a, "traveling", False),
        "travel_dst": getattr(a, "travel_dst", 0),
        "travel_eta": getattr(a, "travel_eta", 0),
        "pos": list(a.pos),
    } for a in w.agents]

    tracked = ["food","wood","ore","stone","tools","cloth",
               "bread","plank","ingot","garment","charcoal",
               "furniture","scimitar","ring","brick","sculpture",
               "banner","wagon","lockbox","ale","jerky"]
    market_data = {}
    for g in tracked:
        if g in w.market.stock:
            market_data[g] = {
                "stock": w.market.stock[g],
                "mid": round(w.market.mid_price(g), 2),
                "buy": round(w.market.buy_price(g), 2),
                "sell": round(w.market.sell_price(g), 2),
            }

    _snap_cache = {
        "t": w.t,
        "merchant_town_id": w.merchant_town_id,
        "merchant_town_name": w.towns[w.merchant_town_id].name,
        "market_gold": round(w.market.gold, 2),
        "num_regions": len(getattr(world, "regions", [None])),
        "active_region": getattr(world, "active_region", 0),
        "towns": towns_data,
        "agents": agents_data,
        "market": market_data,
    }
    _snap_turn = w.t
    return _snap_cache


def agent_detail(name: str) -> dict | None:
    """heavy detail for one agent -- only sent when user clicks"""
    w = world.current() if hasattr(world, "current") else world
    a = next((x for x in w.agents if x.name == name), None)
    if a is None:
        return None

    opinions = []
    for who, v in a.trust.items():
        if who == a.name:
            continue
        score = int(round((v - 0.50) * 200.0))
        if abs(score) > 10:
            opinions.append({"name": who, "score": score})
    opinions.sort(key=lambda x: abs(x["score"]), reverse=True)

    return {
        "name": a.name, "job": a.job,
        "gold": round(a.gold, 2),
        "town_id": a.town_id,
        "town_name": w.towns[a.town_id].name,
        "status": round(a.status, 3),
        "social_class": a.social_class,
        "honesty": round(a.honesty, 2),
        "greed": round(a.greed, 2),
        "sociability": round(a.sociability, 2),
        "vengefulness": round(a.vengefulness, 2),
        "inv": {g: q for g, q in a.inv.items() if q > 0},
        "tags": {k: round(v, 2) for k, v in a.tags.items()},
        "friends": sorted(list(a.friends)),
        "enemies": sorted(list(a.enemies)),
        "opinions": opinions[:40],
        "grudges": [{"target": g.target, "strength": round(g.strength, 2), "reason": g.reason}
                    for g in sorted(a.grudges.values(), key=lambda g: g.strength, reverse=True)][:20],
        "memories": [{"t": m.t, "kind": m.kind, "content": m.content}
                     for m in reversed(a.memory[-60:])],
        "rumors": [{"subject": r.subject, "claim": r.claim, "confidence": round(r.confidence, 2), "last_updated": r.last_updated}
                   for _, r in sorted(a.rumors.items(), key=lambda kv: kv[1].last_updated, reverse=True)[:30]],
        "goals": [{"size": g.size, "good": g.good, "qty": g.qty,
                   "have": a.inv.get(g.good, 0), "deadline": g.deadline_t,
                   "resolved": g.resolved, "succeeded": g.succeeded}
                  for g in a.goals][:15],
        "goal_success": dict(a.goal_success),
        "goal_fail": dict(a.goal_fail),
        "debts_owed": dict(a.debts_owed),
    }


def _process_logs(logs: list[str], t: int) -> list[dict]:
    mark = " ⟦META:"
    return [{"t": t, "text": line[:line.rfind(mark)] if mark in line else line} for line in logs]


# ── routes ─────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)


# ── socketio handlers ─────────────────────────────────────────

@socketio.on("connect")
def handle_connect():
    with sim_lock:
        emit("full_state", snapshot())
        emit("event_log", _events_all[-200:])

@socketio.on("request_state")
def handle_request_state():
    with sim_lock:
        emit("full_state", snapshot())

@socketio.on("request_agent")
def handle_request_agent(data):
    with sim_lock:
        detail = agent_detail(data.get("name", ""))
    if detail:
        emit("agent_detail", detail)

@socketio.on("tick_once")
def handle_tick_once():
    global _snap_cache, _snap_turn
    with sim_lock:
        logs = world.tick()
        _snap_cache = None
        new_events = _process_logs(logs, world.t)
        _events_all.extend(new_events)
        if len(_events_all) > MAX_EVENTS:
            del _events_all[:-MAX_EVENTS]
        emit("full_state", snapshot())
        emit("new_events", new_events[-50:])

@socketio.on("set_speed")
def handle_set_speed(data):
    global sim_speed
    sim_speed = max(0.0, min(200.0, float(data.get("speed", 1.0))))

@socketio.on("toggle_run")
def handle_toggle_run():
    global sim_running
    sim_running = not sim_running
    socketio.emit("run_state", {"running": sim_running})

@socketio.on("set_region")
def handle_set_region(data):
    with sim_lock:
        if hasattr(world, "active_region"):
            world.active_region = int(data.get("region", 0))
        emit("full_state", snapshot())


# ── background: sim thread ────────────────────────────────────

def sim_loop():
    """runs ticks at target speed, completely decoupled from UI"""
    global _snap_cache, _snap_turn
    acc = 0.0
    last = time.monotonic()
    while True:
        now = time.monotonic()
        dt = now - last
        last = now

        if sim_running and sim_speed > 0:
            acc += dt * sim_speed
            if acc > 30.0:
                acc = 30.0  # cap to prevent spiral of death
            while acc >= 1.0:
                acc -= 1.0
                with sim_lock:
                    logs = world.tick()
                    _snap_cache = None
                    new_events = _process_logs(logs, world.t)
                    _events_buffer.extend(new_events)
                    _events_all.extend(new_events)
                    if len(_events_all) > MAX_EVENTS:
                        del _events_all[:-MAX_EVENTS]
                time.sleep(0)  # yield between ticks so other threads can grab the lock

        time.sleep(0.002)


# ── background: UI push thread ────────────────────────────────

def ui_push_loop():
    """pushes state to browser at throttled rate, only when something changed"""
    last_push_turn = -1
    while True:
        time.sleep(MIN_FRAME_DT)

        with sim_lock:
            current_turn = world.t
            has_new_events = len(_events_buffer) > 0

            if current_turn == last_push_turn and not has_new_events:
                continue

            last_push_turn = current_turn
            snap = snapshot()
            new_events = list(_events_buffer[-50:])
            _events_buffer.clear()

        socketio.emit("full_state", snap)
        if new_events:
            socketio.emit("new_events", new_events)


# ── main ───────────────────────────────────────────────────────

def main():
    socketio.start_background_task(sim_loop)
    socketio.start_background_task(ui_push_loop)
    print("\n  Town Sim web UI")
    print("  http://localhost:5000\n")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)

if __name__ == "__main__":
    main()