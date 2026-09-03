"""Safety invariants on hand-built states. No episode is run.

These cover the losses the rules call unrecoverable (weeds, escaped animals) and
the ones that silently zero the score (unsold produce, dropped market orders).
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("cand", str(ROOT / "main.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

PRODUCTS = M.PRODUCTS
FAILS = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}   {detail}")
        FAILS.append(name)


def board(n=10, quads=("NW", "NE", "SW", "SE")):
    def q(x, y):
        h = n // 2
        return ("N" if y < h else "S") + ("W" if x < h else "E")
    return [[None if q(x, y) in quads else "LOCKED" for x in range(n)] for y in range(n)]


def goose(day, unfed, yu=0):
    return {"kind": "COOP", "animal": "GOOSE", "placed_day": max(0, day - 8),
            "yield_units": yu, "fed_today": False, "consecutive_unfed": unfed,
            "cared_today": False, "fertilizer_available": False,
            "pending_care_bonus": 0}


def plant(crop, day, age, cu, yu=1):
    return {"kind": "PLANT", "crop": crop, "planted_day": day - age,
            "watered_today": False, "consecutive_unwatered": cu,
            "yield_units": yu, "max_lifespan_step": -1 if crop in ("TOMATO", "STRAWBERRY")
            else (day - age + M.CROPS[crop]["maxday"] + 1) * 24,
            "fertilized_until_day": -1}


def mk(day, hour, tiles, unit_pos, unit_invs, shed, seeds, money=20000,
       player=0, opp=None):
    n = len(tiles)
    me = {"money": float(money), "tiles": tiles, "farmer": list(unit_pos[0]),
          "hands": [list(p) for p in unit_pos[1:]],
          "unlocked_quadrants": ["NW", "NE", "SW", "SE"],
          "hires_today": len(unit_pos) - 1}
    other = {"money": 3000.0, "tiles": opp or board(n), "farmer": [4, 4],
             "hands": [], "unlocked_quadrants": ["NW"], "hires_today": 0}
    farms = [me, other] if player == 0 else [other, me]
    inv = {p: 10000 for p in PRODUCTS}
    return {"player": player, "day": day, "hour": hour, "step": day * 24 + hour,
            "farms": farms,
            "market": {"inventory": inv,
                       "prices": {p: M.price_at(p, inv[p]) for p in PRODUCTS}},
            "town": {"unlocked_shops": ["BAKERY", "PET_CAFE"]},
            "private": {"shed": dict(shed), "seeds": dict(seeds),
                        "inventories": [dict(i) for i in unit_invs]}}


def ops(act):
    return [act["farmer"]] + act["hands"]


print("\n[1] a herd one day from escaping, wheat in the shed, none in hand")
t = board()
for i in range(12):
    t[i // 10][i % 10] = goose(10, unfed=1)
# also give it a field full of thirsty plants, which is what used to win the
# allocation and starve the herd
for i in range(40, 80):
    t[i // 10][i % 10] = plant("WHEAT", 10, 2, 1)
obs = mk(10, 0, t, [(4, 4)] * 9, [{}] * 9, {"WHEAT": 60}, {})
a = M.agent(obs)
picks = [o for o in ops(a) if o[0] == "PICKUP" and o[1] == "WHEAT"]
check("units are sent for feed wheat", len(picks) >= 1, f"got {ops(a)[:4]}")

print("\n[2] same herd, wheat already in hand, unit standing on a hungry animal")
obs = mk(10, 0, t, [(0, 0)] + [(4, 4)] * 8, [{"WHEAT": 20}] + [{}] * 8,
         {"WHEAT": 60}, {})
a = M.agent(obs)
check("the unit on the animal FEEDs it", a["farmer"][0] == "FEED", str(a["farmer"]))

print("\n[3] a plant one day from becoming a weed, unit standing on it")
t2 = board()
t2[0][0] = plant("STRAWBERRY", 12, 6, 1)
obs = mk(12, 0, t2, [(0, 0)], [{}], {}, {})
a = M.agent(obs)
check("the unit on the plant WATERs it", a["farmer"][0] == "WATER", str(a["farmer"]))

print("\n[4] no plant is ever left to die while a unit idles")
t3 = board()
for i in range(6):
    t3[9][i] = plant("MELON", 20, 8, 1)
obs = mk(20, 20, t3, [(0, 9)] * 6, [{}] * 6, {}, {})
a = M.agent(obs)
n_water = sum(1 for o in ops(a) if o[0] == "WATER")
check("thirsty plants are watered/approached", n_water >= 1 or
      all(o[0] in ("NORTH", "SOUTH", "EAST", "WEST", "WATER") for o in ops(a)),
      str(ops(a)))

print("\n[5] final day: everything in the shed is sold and hands walk it in")
t4 = board()
for i in range(20):
    t4[i // 10][i % 10] = goose(29, unfed=0, yu=4)
shed = {"EGG": 40, "WHEAT": 25, "MELON": 6, "FERTILIZER": 9}
obs = mk(29, 17, t4, [(0, 0)] * 5, [{"EGG": 9}] * 5, shed, {})
a = M.agent(obs)
sold = {o[1]: o[2] for o in a["market"] if o[0] == "SELL"}
check("every stocked product is dumped", all(sold.get(k, 0) >= v for k, v in shed.items()),
      f"orders {a['market']}")
check("no buying on the last day",
      not any(o[0].startswith("BUY") for o in a["market"]), str(a["market"]))
drops = [o for o in ops(a) if o[0] == "DROP"]
moves = [o for o in ops(a) if o[0] in ("NORTH", "SOUTH", "EAST", "WEST")]
check("carried produce is walked to the shed", len(drops) + len(moves) == 5, str(ops(a)))

print("\n[6] PLANT requests never exceed seeds held (engine drops all of them)")
bad = 0
t5 = board()
for k, (sd, expect) in enumerate([({"WHEAT": 1}, 1), ({"CARROT": 2}, 2), ({}, 0)]):
    obs = mk(5, 5, t5, [(4, 4)] * 8, [{}] * 8, {}, sd, money=0)
    a = M.agent(obs)
    dem = {}
    for o in ops(a):
        if o[0] == "PLANT":
            dem[o[1]] = dem.get(o[1], 0) + 1
    for c, cnt in dem.items():
        if cnt > sd.get(c, 0):
            bad += 1
check("PLANT demand <= seeds on hand", bad == 0, f"{bad} violations")

print("\n[7] market queue never exceeds the 10-order cap, both seats")
worst = 0
for player in (0, 1):
    for day in range(30):
        for hour in (0, 1, 2, 11, 23):
            obs = mk(day, hour, t, [(4, 4)] * 13, [{}] * 13,
                     {p: 11 for p in PRODUCTS}, {c: 5 for c in M.CROPS},
                     money=500000, player=player)
            a = M.agent(obs)
            worst = max(worst, len(a["market"]))
            if len(a["hands"]) != 12:
                FAILS.append("hands length")
check("market orders <= 10", worst <= 10, f"worst {worst}")
check("hands length always matches", "hands length" not in FAILS)

print("\n[8] an unfed-risk animal is never ignored when wheat exists anywhere")
t6 = board()
t6[4][3] = goose(15, unfed=1)
for i in range(60, 100):
    t6[i // 10][i % 10] = plant("WHEAT", 15, 3, 1)
for hour in range(0, 24, 4):
    obs = mk(15, hour, t6, [(4, 4)] * 13, [{}] * 13, {"WHEAT": 40}, {})
    a = M.agent(obs)
    has = any(o[0] == "PICKUP" and o[1] == "WHEAT" for o in ops(a))
    if not has:
        FAILS.append(f"no feed run at hour {hour}")
check("a feed run is launched at every hour of the day",
      not any(f.startswith("no feed run") for f in FAILS))

print()
if FAILS:
    print(f"{len(FAILS)} FAILURES: {FAILS}")
    sys.exit(1)
print("all invariants hold")
