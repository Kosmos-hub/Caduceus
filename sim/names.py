# sim/names.py
# Tuareg-inspired name generation
# cut from town_sim.py

from __future__ import annotations

import random
from typing import List


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
