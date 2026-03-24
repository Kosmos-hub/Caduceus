# town_sim.py
# thin entry point -- all logic lives in sim/
# kept for backwards compatibility with ui_screens.py imports

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import random

from sim.config import SEED, TURNS, NUM_AGENTS, edible_count
from sim.setup import make_multiverse


def run_ui(world, *, title: str = "Town Sim") -> None:
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
