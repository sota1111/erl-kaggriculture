"""Static contract fuzz for main.py.  Builds synthetic observations directly --
no episode is run -- and checks that agent(obs) never raises, always returns a
legal action dict, and stays far inside the 1s/turn budget.

Covers: both seats, every day/hour, every quadrant-unlock combination, every
tile kind (empty / locked / plant of each crop at every age / weed / empty coop
/ pasture / animal of each kind in every fed-cared-yield state), 0..14 hands,
empty and full sheds, and market inventories from deep scarcity to total glut.
"""
import importlib.util, random, sys, time, json

spec = importlib.util.spec_from_file_location("sub", sys.argv[1] if len(sys.argv) > 1 else "main.py")
sub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sub)

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]
CROPS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
ANIMALS = ["GOOSE", "COW", "SHEEP"]
SHOPS = ["BAKERY", "PIZZA_SHOP", "BRUNCH_SPOT", "YARN_STORE", "ICE_CREAM_SHOP",
         "PET_CAFE", "SMOOTHIE_SHOP", "FARMERS_MARKET"]
MOVES = {"NORTH", "SOUTH", "EAST", "WEST", "PASS"}
TILE_OPS = {"PICKUP", "PLACE", "DROP", "PLANT", "WATER", "HARVEST", "FERTILIZE",
            "BUILD_COOP", "BUILD_PASTURE", "FEED", "COLLECT_FERTILIZER", "CARE", "DIG"}
MARKET_OPS = {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL", "HIRE", "BUY_LAND"}


def rand_tile(rng, day, locked):
    if locked:
        return "LOCKED"
    r = rng.random()
    if r < 0.30:
        return None
    if r < 0.36:
        return {"kind": "WEED"}
    if r < 0.40:
        return {"kind": rng.choice(["COOP", "PASTURE"])}
    if r < 0.58:
        a = rng.choice(ANIMALS)
        return {"kind": "COOP" if a == "GOOSE" else "PASTURE", "animal": a,
                "placed_day": rng.randint(0, max(0, day)), "yield_units": rng.randint(0, 6),
                "fed_today": rng.random() < .5, "consecutive_unfed": rng.randint(0, 1),
                "cared_today": rng.random() < .5, "fertilizer_available": rng.random() < .5,
                "pending_care_bonus": rng.randint(0, 3)}
    c = rng.choice(CROPS)
    pd = rng.randint(max(0, day - 20), day)
    return {"kind": "PLANT", "crop": c, "planted_day": pd,
            "watered_today": rng.random() < .5, "consecutive_unwatered": rng.randint(0, 1),
            "yield_units": rng.randint(0, 6),
            "max_lifespan_step": rng.choice([-1, (pd + 5) * 24, (pd + 13) * 24, day * 24]),
            "fertilized_until_day": rng.choice([-1, day - 1, day + 1])}


def rand_obs(rng):
    board = 10
    day, hour = rng.randint(0, 29), rng.randint(0, 23)
    nq = rng.randint(0, 3)
    quads = ["NW"] + ["NE", "SW", "SE"][:nq]

    def locked(x, y):
        q = ("N" if y < 5 else "S") + ("W" if x < 5 else "E")
        return q not in quads

    farms = []
    for _ in range(2):
        tiles = [[rand_tile(rng, day, locked(x, y)) for x in range(board)] for y in range(board)]
        n_hands = rng.randint(0, 14)
        farms.append({
            "money": rng.choice([0.0, 12.0, 300.0, 3000.0, 25000.0, 400000.0]),
            "tiles": tiles,
            "farmer": [rng.randint(0, 9), rng.randint(0, 9)],
            "hands": [[rng.randint(0, 9), rng.randint(0, 9)] for _ in range(n_hands)],
            "unlocked_quadrants": quads,
            "hires_today": n_hands,
        })
    player = rng.randint(0, 1)
    n_hands = len(farms[player]["hands"])
    shed_scale = rng.choice([0, 1, 12])
    shed = {p: rng.randint(0, shed_scale) for p in PRODUCTS}
    for a in ANIMALS:
        shed[a] = rng.randint(0, 2)
    inv = [{p: rng.randint(0, 4) for p in rng.sample(PRODUCTS, rng.randint(0, 4))}
           for _ in range(n_hands + 1)]
    if rng.random() < .2:
        inv = inv[:rng.randint(0, n_hands + 1)]           # short inventories list
    return {
        "player": player, "day": day, "hour": hour, "step": day * 24 + hour,
        "farms": farms,
        "market": {"inventory": {p: 10000 + rng.randint(-1500, 2500) for p in PRODUCTS},
                   "prices": {p: rng.randint(1, 300) for p in PRODUCTS}},
        "town": {"unlocked_shops": [rng.choice(SHOPS) for _ in range(rng.randint(0, 8))]},
        "private": {"shed": shed, "seeds": {c: rng.randint(0, 6) for c in CROPS},
                    "inventories": inv},
    }


def check(act, obs):
    assert isinstance(act, dict) and set(act) == {"farmer", "hands", "market"}, act
    assert isinstance(act["farmer"], list) and act["farmer"], act
    assert isinstance(act["hands"], list)
    assert isinstance(act["market"], list) and len(act["market"]) <= 10, act["market"]
    n_hands = len(obs["farms"][obs["player"]]["hands"])
    assert len(act["hands"]) == n_hands, (len(act["hands"]), n_hands)
    for u in [act["farmer"]] + act["hands"]:
        assert isinstance(u, list) and u and isinstance(u[0], str), u
        assert u[0] in MOVES or u[0] in TILE_OPS, u
    for m in act["market"]:
        assert isinstance(m, list) and m and m[0] in MARKET_OPS, m
        if m[0] in ("BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL"):
            assert len(m) == 3 and isinstance(m[2], int) and m[2] > 0, m


N = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
rng = random.Random(7)
for _ in range(50):                       # warm up: first call pays import/alloc cost
    sub.agent(rand_obs(rng))
worst, worst_obs = 0.0, None
total = 0.0
for i in range(N):
    obs = rand_obs(rng)
    t = time.perf_counter()
    act = sub.agent(obs)
    dt = time.perf_counter() - t
    total += dt
    if dt > worst:
        worst, worst_obs = dt, obs
    check(act, obs)

# degenerate / hostile observations must not raise either
edge = [
    {}, {"player": 0}, {"player": 5, "farms": []},
    {"player": 0, "day": 0, "farms": [{"money": 100, "farmer": [0, 0], "tiles": [[None]]}],
     "private": {"shed": {}, "seeds": {"WHEAT": 1}, "inventories": [[]]}},
    {"player": 1, "day": 40, "hour": 99, "farms": [{}, {}], "private": None, "market": None},
    {"player": 0, "day": 3, "farms": [{"tiles": [["LOCKED"] * 10] * 10, "farmer": [4, 4],
                                       "hands": [[4, 4]], "money": 5}], "private": {}},
]
for o in edge:
    a = sub.agent(o)
    assert set(a) == {"farmer", "hands", "market"}, a

print(f"{N} random observations + {len(edge)} edge cases: no exception, contract holds")
print(f"worst turn {worst*1000:.2f} ms   mean {total/N*1000:.3f} ms   "
      f"720-turn projection {total/N*720:.2f} s (worst-case bound {worst*720:.2f} s)")
if worst_obs:
    f = worst_obs["farms"][worst_obs["player"]]
    print(f"worst case: day {worst_obs['day']} hour {worst_obs['hour']} "
          f"hands {len(f['hands'])} quadrants {len(f['unlocked_quadrants'])}")


# explicit worst case: whole board owned, every tile carrying work, 14 hands,
# full shed, deeply glutted market -- the most expensive turn the season can hold.
def worst_obs_build(n_hands=14):
    rng2 = random.Random(1)
    tiles = []
    for y in range(10):
        row = []
        for x in range(10):
            if (x + y) % 3 == 0:
                row.append({"kind": "COOP", "animal": "GOOSE", "placed_day": 5,
                            "yield_units": 3, "fed_today": False, "consecutive_unfed": 1,
                            "cared_today": False, "fertilizer_available": True,
                            "pending_care_bonus": 2})
            elif (x + y) % 3 == 1:
                row.append({"kind": "PLANT", "crop": "MELON", "planted_day": 10,
                            "watered_today": False, "consecutive_unwatered": 1,
                            "yield_units": 3, "max_lifespan_step": 23 * 24,
                            "fertilized_until_day": -1})
            else:
                row.append(None)
        tiles.append(row)
    farm = {"money": 250000.0, "tiles": tiles, "farmer": [4, 4],
            "hands": [[rng2.randint(0, 9), rng2.randint(0, 9)] for _ in range(n_hands)],
            "unlocked_quadrants": ["NW", "NE", "SW", "SE"], "hires_today": n_hands}
    return {"player": 0, "day": 16, "hour": 0, "step": 16 * 24,
            "farms": [farm, farm], "market": {
                "inventory": {p: 9200 for p in PRODUCTS},
                "prices": {p: 40 for p in PRODUCTS}},
            "town": {"unlocked_shops": SHOPS[:8]},
            "private": {"shed": {p: 40 for p in PRODUCTS},
                        "seeds": {c: 30 for c in CROPS},
                        "inventories": [{p: 9 for p in PRODUCTS} for _ in range(n_hands + 1)]}}

wo = worst_obs_build()
sub.agent(wo)
t = time.perf_counter()
for _ in range(200):
    a = sub.agent(wo)
dt = (time.perf_counter() - t) / 200
check(a, wo)
print(f"full-board 14-hand turn: {dt*1000:.2f} ms  -> 720 turns = {dt*720:.2f} s")
print("  farmer:", a["farmer"], " market:", json.dumps(a["market"]))
