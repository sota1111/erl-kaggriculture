"""Adversarial worst-case timing: the densest board the engine can present.

100 unlocked tiles, 12 hands (the hire cap), every tile occupied and demanding
attention at once, at every hour of every day. No episode is run.
"""
from __future__ import annotations
import importlib.util, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CROPS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER"]


def load(path):
    spec = importlib.util.spec_from_file_location("cand", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def dense_farm(day, mode):
    """mode 0: all plants thirsty. 1: all animals hungry. 2: half/half + weeds."""
    tiles = []
    for y in range(10):
        row = []
        for x in range(10):
            i = y * 10 + x
            if mode == 1 or (mode == 2 and i % 2 == 0):
                row.append({"kind": "COOP", "animal": "GOOSE",
                            "placed_day": max(0, day - 6), "yield_units": 3,
                            "fed_today": False, "consecutive_unfed": 1,
                            "cared_today": False, "fertilizer_available": True,
                            "pending_care_bonus": 1})
            elif mode == 2 and i % 7 == 0:
                row.append({"kind": "WEED"})
            else:
                row.append({"kind": "PLANT", "crop": CROPS[i % 5],
                            "planted_day": max(0, day - 3),
                            "watered_today": False, "consecutive_unwatered": 1,
                            "yield_units": 2, "max_lifespan_step": -1,
                            "fertilized_until_day": -1})
        tiles.append(row)
    return tiles


def main():
    agent = load(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "main.py"))
    worst = 0.0
    worst_tag = ""
    total = 0.0
    calls = 0
    for mode in (0, 1, 2):
        for day in range(30):
            for hour in range(24):
                for player in (0, 1):
                    tiles = dense_farm(day, mode)
                    farm = {"money": 250000.0, "tiles": tiles, "farmer": [4, 4],
                            "hands": [[(i * 3) % 10, (i * 7) % 10] for i in range(12)],
                            "unlocked_quadrants": ["NW", "NE", "SW", "SE"],
                            "hires_today": 12}
                    farms = [farm, farm] if player == 0 else [farm, farm]
                    obs = {
                        "player": player, "day": day, "hour": hour,
                        "step": day * 24 + hour, "farms": farms,
                        "market": {"inventory": {p: 9800 for p in PRODUCTS},
                                   "prices": {p: 40 for p in PRODUCTS}},
                        "town": {"unlocked_shops": ["BAKERY"] * 8},
                        "private": {
                            "shed": {p: 9 for p in PRODUCTS} | {"GOOSE": 3, "COW": 2, "SHEEP": 2},
                            "seeds": {c: 20 for c in CROPS},
                            "inventories": [{"WHEAT": 5, "FERTILIZER": 5, "EGG": 9}] * 13,
                        },
                    }
                    t0 = time.perf_counter()
                    act = agent(obs)
                    dt = time.perf_counter() - t0
                    total += dt
                    calls += 1
                    assert set(act) == {"farmer", "hands", "market"}
                    assert len(act["hands"]) == 12
                    assert len(act["market"]) <= 10
                    if dt > worst:
                        worst, worst_tag = dt, f"mode={mode} day={day} hour={hour} p={player}"
    print(f"{calls} dense turns")
    print(f"  worst {worst*1000:.2f} ms  ({worst_tag})")
    print(f"  mean  {total/calls*1000:.2f} ms")
    print(f"  720-turn season at the worst turn: {worst*720:.2f} s "
          f"(limit is 1.00 s per turn)")


if __name__ == "__main__":
    main()
