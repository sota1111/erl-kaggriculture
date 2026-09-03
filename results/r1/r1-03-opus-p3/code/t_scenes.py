"""Hand-built single-turn scenarios: does the controller do the thing the design
says it should?  No episode is run -- each case is one observation in, one
action out.  These are the behavioural checks that replace playing games.
"""
import importlib.util, sys, json

spec = importlib.util.spec_from_file_location("sub", "main.py")
sub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sub)

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]
CROPS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
FAILED = []


def board(quads=("NW",), fill=None):
    def locked(x, y):
        q = ("N" if y < 5 else "S") + ("W" if x < 5 else "E")
        return q not in quads
    return [[("LOCKED" if locked(x, y) else (fill(x, y) if fill else None))
             for x in range(10)] for y in range(10)]


def obs(tiles, player=0, day=0, hour=0, money=3000.0, hands=(), shed=None, seeds=None,
        inv=None, minv=None, shops=(), quads=("NW",), hires=None):
    n = len(hands)
    farm = {"money": money, "tiles": tiles, "farmer": [4, 4], "hands": [list(h) for h in hands],
            "unlocked_quadrants": list(quads), "hires_today": n if hires is None else hires}
    other = {"money": 3000.0, "tiles": board(quads), "farmer": [4, 4], "hands": [],
             "unlocked_quadrants": list(quads), "hires_today": 0}
    farms = [farm, other] if player == 0 else [other, farm]
    inventories = [dict(x) for x in (inv or [{}] * (n + 1))]
    return {"player": player, "day": day, "hour": hour, "step": day * 24 + hour,
            "farms": farms,
            "market": {"inventory": dict(minv or {p: 10000 for p in PRODUCTS}),
                       "prices": {p: 1 for p in PRODUCTS}},
            "town": {"unlocked_shops": list(shops)},
            "private": {"shed": dict(shed or {}), "seeds": dict(seeds or {}),
                        "inventories": inventories}}


def ops(a):
    return [u[0] for u in [a["farmer"]] + a["hands"]]


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ("   " + detail if detail else ""))
    if not cond:
        FAILED.append(name)


def plant(crop, planted_day, **kw):
    t = {"kind": "PLANT", "crop": crop, "planted_day": planted_day, "watered_today": False,
         "consecutive_unwatered": 0, "yield_units": 1, "max_lifespan_step": -1,
         "fertilized_until_day": -1}
    t.update(kw)
    return t


def animal(kind, placed_day, **kw):
    t = {"kind": "COOP" if kind == "GOOSE" else "PASTURE", "animal": kind,
         "placed_day": placed_day, "yield_units": 0, "fed_today": False,
         "consecutive_unfed": 0, "cared_today": False, "fertilizer_available": False,
         "pending_care_bonus": 0}
    t.update(kw)
    return t


print("\n== opening ==")
a = sub.agent(obs(board()))
m = a["market"]
check("day 0 hires hands", sum(1 for o in m if o[0] == "HIRE") >= 2, str(m))
check("day 0 buys seed", any(o[0] == "BUY_SEED" for o in m))
check("day 0 buys the NE quadrant", any(o[0] == "BUY_LAND" for o in m), json.dumps(m))

a = sub.agent(obs(board(), money=900.0))
check("no land purchase we cannot stock", not any(o[0] == "BUY_LAND" for o in a["market"]))

print("\n== the two unrecoverable states ==")
t = board()
t[0][0] = plant("WHEAT", 0, consecutive_unwatered=1)
a = sub.agent(obs(t, hands=[[4, 4]], seeds={"WHEAT": 5}))
check("a plant that weeds tonight is watered", "WATER" in ops(a) or "WEST" in ops(a) or "NORTH" in ops(a),
      str(ops(a)))
t = board()
t[4][4] = plant("WHEAT", 0, consecutive_unwatered=1)
a = sub.agent(obs(t, seeds={"WHEAT": 5}))
check("...even standing on it, before anything else", a["farmer"] == ["WATER"], str(a["farmer"]))

t = board()
t[4][4] = animal("GOOSE", 0, consecutive_unfed=1)
a = sub.agent(obs(t, inv=[{"WHEAT": 3}], shed={"WHEAT": 10}))
check("an animal that escapes tonight is fed", a["farmer"] == ["FEED"], str(a["farmer"]))

t = board()
t[4][4] = animal("GOOSE", 0, consecutive_unfed=1)
a = sub.agent(obs(t, inv=[{}], shed={"WHEAT": 10}, hour=1))
check("no wheat in hand -> picks it up from the shed",
      a["farmer"][:2] == ["PICKUP", "WHEAT"], str(a["farmer"]))
a = sub.agent(obs(t, inv=[{}], shed={}, hour=1, money=5000.0))
check("no wheat anywhere -> buys it",
      any(o[:2] == ["BUY_PRODUCT", "WHEAT"] for o in a["market"]), json.dumps(a["market"]))

print("\n== harvest timing ==")
t = board()
t[4][4] = plant("WHEAT", 0, watered_today=True, yield_units=4)
a = sub.agent(obs(t, day=4, hour=12))
check("wheat harvested at max_yield_day", a["farmer"] == ["HARVEST"], str(a["farmer"]))
t = board()
t[4][4] = plant("WHEAT", 0, watered_today=False, yield_units=3)
a = sub.agent(obs(t, day=4, hour=12))
check("...but watered first, the bonus lands the same turn", a["farmer"] == ["WATER"], str(a["farmer"]))
t = board()
t[4][4] = plant("MELON", 0, watered_today=True, yield_units=3)
a = sub.agent(obs(t, day=6, hour=12))
check("an unripe melon is not harvested", a["farmer"] != ["HARVEST"], str(a["farmer"]))

print("\n== market discipline ==")
glut = {p: 10000 for p in PRODUCTS}
glut["MELON"] = 10160                                    # marginal melon is $1
a = sub.agent(obs(board(), day=15, hour=12, shed={"MELON": 20}, minv=glut))
check("melon is not dumped at the floor",
      not any(o[0] == "SELL" and o[1] == "MELON" for o in a["market"]), json.dumps(a["market"]))
a = sub.agent(obs(board(), day=29, hour=12, shed={"MELON": 20}, minv=glut))
check("...but everything is liquidated on the last day",
      any(o[:3] == ["SELL", "MELON", 20] for o in a["market"]), json.dumps(a["market"]))

t = board()
t[4][4] = animal("GOOSE", 0, fed_today=True)
a = sub.agent(obs(t, day=10, hour=12, shed={"WHEAT": 6}))
sold = [o for o in a["market"] if o[0] == "SELL" and o[1] == "WHEAT"]
kept = 6 - (sold[0][2] if sold else 0)
check("the herd's feed is never sold out from under it", kept >= 4, "kept %d" % kept)
a = sub.agent(obs(t, day=10, hour=12, shed={"WHEAT": 3}))
check("...and a thin larder is not touched at all",
      not [o for o in a["market"] if o[0] == "SELL" and o[1] == "WHEAT"], json.dumps(a["market"]))
a = sub.agent(obs(t, day=10, hour=12, shed={"WHEAT": 60}))
sold = [o for o in a["market"] if o[0] == "SELL" and o[1] == "WHEAT"]
check("surplus wheat is sold", sold and sold[0][2] <= 60 - 5, json.dumps(sold))

print("\n== the shop draw moves the plan ==")
yarn = ["YARN_STORE"] * 3
t = board(quads=("NW", "NE", "SW", "SE"))
for y in range(5):
    for x in range(5):
        t[y][x] = plant("WHEAT", 0, watered_today=True)
a1 = sub.agent(obs(t, day=8, hour=8, money=30000.0, quads=("NW", "NE", "SW", "SE"), shops=yarn))
a0 = sub.agent(obs(t, day=8, hour=8, money=30000.0, quads=("NW", "NE", "SW", "SE"), shops=[]))
buy1 = [o for o in a1["market"] if o[0] == "BUY_ANIMAL"]
buy0 = [o for o in a0["market"] if o[0] == "BUY_ANIMAL"]
n1 = sum(o[2] for o in buy1 if o[1] == "SHEEP")
n0 = sum(o[2] for o in buy0 if o[1] == "SHEEP")
check("three yarn stores -> buy sheep", n1 >= 3, "bought %d" % n1)
check("no yarn store -> buy far fewer", n0 < n1, "bought %d vs %d" % (n0, n1))

print("\n== housekeeping ==")
t = board()
t[4][4] = {"kind": "COOP"}
a = sub.agent(obs(t, day=5, inv=[{"GOOSE": 1}], hour=6))
check("a carried goose is placed on an empty coop",
      a["farmer"] == ["PLACE", "GOOSE"], str(a["farmer"]))
t2 = board()
t2[3][3] = {"kind": "COOP"}
a = sub.agent(obs(t2, day=5, shed={"GOOSE": 1}, hour=6))
check("a shed goose is fetched by a courier",
      a["farmer"][:2] == ["PICKUP", "GOOSE"], str(a["farmer"]))
t3 = board()
t3[4][4] = {"kind": "COOP"}
a = sub.agent(obs(t3, day=5, hour=6, money=20000.0))
check("a coop we still want stocked is not dug up", a["farmer"] != ["DIG"], str(a["farmer"]))
a = sub.agent(obs(t3, day=23, hour=6, money=20000.0))
check("...but a useless one is reclaimed", a["farmer"] == ["DIG"], str(a["farmer"]))

t = board()
t[4][4] = {"kind": "WEED"}
a = sub.agent(obs(t, day=5, hour=6, seeds={}, money=0.0))
check("weeds get dug", a["farmer"] == ["DIG"], str(a["farmer"]))
t = board()
t[0][0] = {"kind": "WEED"}
a = sub.agent(obs(t, day=5, hour=6, seeds={}, money=0.0))
check("broke and animal-less -> no speculative coops", "BUILD_COOP" not in ops(a), str(ops(a)))

a = sub.agent(obs(board(), day=5, hour=22, seeds={"WHEAT": 9}, money=2000.0))
check("nothing is planted too late to water it", "PLANT" not in ops(a), str(ops(a)))
a = sub.agent(obs(board(), day=5, hour=6, seeds={"WHEAT": 9}, money=2000.0))
check("...but it is planted in time", "PLANT" in ops(a), str(ops(a)))

print("\n== both seats ==")
t = board(quads=("NW", "NE"))
t[4][4] = plant("CARROT", 3, consecutive_unwatered=1)
for p in (0, 1):
    a = sub.agent(obs(t, player=p, day=5, hour=3, quads=("NW", "NE")))
    check("seat %d waters its own farm" % p, a["farmer"] == ["WATER"], str(a["farmer"]))

print("\n== units spread out instead of piling up ==")
t = board(quads=("NW", "NE", "SW", "SE"))
for y in range(10):
    for x in range(10):
        t[y][x] = plant("WHEAT", 0, watered_today=False)
hands = [[4, 4]] * 12
a = sub.agent(obs(t, day=3, hour=4, money=20000.0, hands=hands,
                  quads=("NW", "NE", "SW", "SE"), seeds={}, inv=[{}] * 13))
check("13 units, 13 distinct jobs", len(ops(a)) == 13, str(ops(a)))
check("most units are working, not idling", ops(a).count("PASS") <= 1, str(ops(a)))

print()
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
print("all scenarios pass")
