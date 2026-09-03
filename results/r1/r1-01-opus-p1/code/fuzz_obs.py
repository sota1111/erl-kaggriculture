"""Static contract fuzzer: hand-built observations, no episode is ever run.

Generates random-but-plausible observations across the whole state space the
engine can produce (both seats, every day/hour, locked and unlocked quadrants,
weeds, decaying plants, escaped animals, empty and full sheds, missing keys) and
asserts the agent returns a legal action dict, fast, without raising.

    .venv/bin/python code/fuzz_obs.py [--n 20000]
"""
from __future__ import annotations
import argparse, importlib.util, random, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CROPS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
ANIMALS = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}
PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER"]
SHOPS = ["BAKERY", "PIZZA_SHOP", "BRUNCH_SPOT", "YARN_STORE",
         "ICE_CREAM_SHOP", "PET_CAFE", "SMOOTHIE_SHOP", "FARMERS_MARKET"]

UNIT_OPS = {"NORTH", "SOUTH", "EAST", "WEST", "PASS", "PICKUP", "PLACE", "DROP",
            "PLANT", "WATER", "HARVEST", "FERTILIZE", "BUILD_COOP",
            "BUILD_PASTURE", "FEED", "COLLECT_FERTILIZER", "CARE", "DIG"}
MARKET_OPS = {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL", "HIRE", "BUY_LAND"}


def load(path):
    spec = importlib.util.spec_from_file_location("cand", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def quad(x, y, n):
    h = n // 2
    return ("N" if y < h else "S") + ("W" if x < h else "E")


def rand_tile(rng, day, n, unlocked, x, y):
    if quad(x, y, n) not in unlocked:
        return "LOCKED"
    r = rng.random()
    if r < 0.28:
        return None
    if r < 0.34:
        return {"kind": "WEED"}
    if r < 0.55:
        kind = rng.choice(["COOP", "PASTURE"])
        if rng.random() < 0.25:
            return {"kind": kind}
        animal = rng.choice([a for a, s in ANIMALS.items() if s == kind])
        return {
            "kind": kind, "animal": animal,
            "placed_day": rng.randint(0, max(0, day)),
            "yield_units": rng.randint(0, 6),
            "fed_today": rng.random() < 0.5,
            "consecutive_unfed": rng.randint(0, 1),
            "cared_today": rng.random() < 0.5,
            "fertilizer_available": rng.random() < 0.5,
            "pending_care_bonus": rng.randint(0, 3),
        }
    crop = rng.choice(CROPS)
    pd = rng.randint(max(0, day - 20), day)
    return {
        "kind": "PLANT", "crop": crop, "planted_day": pd,
        "watered_today": rng.random() < 0.5,
        "consecutive_unwatered": rng.randint(0, 1),
        "yield_units": rng.randint(0, 6),
        "max_lifespan_step": rng.choice([-1, (pd + 5) * 24, (pd + 12) * 24]),
        "fertilized_until_day": rng.choice([-1, day - 1, day, day + 2]),
    }


def make_obs(rng):
    n = rng.choice([10, 10, 10, 10, 6, 4])
    day = rng.randint(0, 29)
    hour = rng.randint(0, 23)
    player = rng.randint(0, 1)
    farms = []
    for _ in range(2):
        unlocked = ["NW"]
        for q in ("NE", "SW", "SE"):
            if rng.random() < 0.55:
                unlocked.append(q)
        tiles = [[rand_tile(rng, day, n, unlocked, x, y) for x in range(n)]
                 for y in range(n)]
        n_hands = rng.randint(0, 13)
        farms.append({
            "money": rng.choice([0.0, 3.0, 250.0, 3000.0, 55000.0, 400000.0]),
            "tiles": tiles,
            "farmer": [rng.randrange(n), rng.randrange(n)],
            "hands": [[rng.randrange(n), rng.randrange(n)] for _ in range(n_hands)],
            "unlocked_quadrants": unlocked,
            "hires_today": rng.randint(0, 13),
        })
    me = farms[player]
    shed_items = rng.randint(0, 3)
    shed = {}
    for _ in range(shed_items):
        shed[rng.choice(PRODUCTS + list(ANIMALS))] = rng.randint(0, 60)
    inventories = [{} for _ in range(len(me["hands"]) + 1)]
    for inv in inventories:
        if rng.random() < 0.5:
            inv[rng.choice(PRODUCTS + list(ANIMALS))] = rng.randint(1, 40)
    minv = {p: 10000 + rng.randint(-1500, 3000) for p in PRODUCTS}
    obs = {
        "player": player, "day": day, "hour": hour,
        "step": day * 24 + hour,
        "farms": farms,
        "market": {"inventory": minv,
                   "prices": {p: max(1, rng.randint(1, 300)) for p in PRODUCTS}},
        "town": {"unlocked_shops": [rng.choice(SHOPS)
                                    for _ in range(rng.randint(0, 8))]},
        "private": {"shed": shed,
                    "seeds": {c: rng.randint(0, 20) for c in CROPS},
                    "inventories": inventories},
    }
    # Occasionally hand the agent a mangled observation on purpose.
    r = rng.random()
    if r < 0.03:
        del obs["market"]
    elif r < 0.06:
        del obs["town"]
    elif r < 0.09:
        obs["private"] = {}
    elif r < 0.11:
        obs["farms"] = [me]
        obs["player"] = 0
    elif r < 0.13:
        obs["private"]["inventories"] = []
    return obs


def check(obs, act):
    assert isinstance(act, dict), "not a dict"
    assert set(act) == {"farmer", "hands", "market"}, f"bad keys {set(act)}"
    assert isinstance(act["farmer"], list) and act["farmer"], "bad farmer"
    assert act["farmer"][0] in UNIT_OPS, f"bad farmer op {act['farmer'][0]}"
    assert isinstance(act["hands"], list)
    farms = obs.get("farms") or []
    p = obs.get("player", 0)
    if farms and p < len(farms):
        want = len(farms[p].get("hands") or [])
        assert len(act["hands"]) == want, f"hands {len(act['hands'])} != {want}"
    for h in act["hands"]:
        assert isinstance(h, list) and h and h[0] in UNIT_OPS, f"bad hand op {h}"
    assert isinstance(act["market"], list)
    assert len(act["market"]) <= 10, f"{len(act['market'])} market orders > 10"
    for o in act["market"]:
        assert isinstance(o, list) and o and o[0] in MARKET_OPS, f"bad order {o}"
        if o[0] in ("BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL"):
            assert len(o) == 3, f"bad order arity {o}"
            assert isinstance(o[2], int) and o[2] > 0, f"bad qty {o}"
            if o[0] == "SELL":
                assert o[1] in PRODUCTS, f"unsellable {o}"
            if o[0] == "BUY_PRODUCT":
                assert o[1] in ("WHEAT", "FERTILIZER"), f"unbuyable {o}"
            if o[0] == "BUY_SEED":
                assert o[1] in CROPS, f"bad seed {o}"
            if o[0] == "BUY_ANIMAL":
                assert o[1] in ANIMALS, f"bad animal {o}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate", nargs="?", default=str(ROOT / "main.py"))
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    agent = load(args.candidate)
    rng = random.Random(args.seed)
    worst = 0.0
    worst_obs = None
    total = 0.0
    for i in range(args.n):
        obs = make_obs(rng)
        t0 = time.perf_counter()
        act = agent(obs)
        dt = time.perf_counter() - t0
        total += dt
        if dt > worst:
            worst, worst_obs = dt, obs
        try:
            check(obs, act)
        except AssertionError as e:
            print(f"FAIL at {i}: {e}\n  day={obs.get('day')} hour={obs.get('hour')} "
                  f"player={obs.get('player')}\n  act={act}")
            return 1
    print(f"{args.n} synthetic observations: contract OK")
    print(f"  worst turn {worst*1000:.2f} ms   mean {total/args.n*1000:.3f} ms")
    if worst_obs is not None:
        f = worst_obs["farms"][worst_obs["player"]]
        print(f"  worst case: board {len(f['tiles'])}, hands {len(f['hands'])}, "
              f"quadrants {f['unlocked_quadrants']}")
    print(f"  720-turn projection at worst-case: {worst*720:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
