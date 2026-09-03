"""What a tile-day is worth, per crop and per animal, and hence the mix.

Combines the two things measured elsewhere: the marginal price a product fetches
when sold at its revenue-maximising rate (code/a_plan.py) and the units a tile
produces per day (env CROPS/ANIMALS tables + the watering/care rules).  Nothing
here runs an episode; it is the crop table times the price table.
"""
import sys, random, collections, statistics
sys.path.insert(0, ".venv/lib/python3.12/site-packages")
from kaggle_environments.envs.kaggriculture.kaggriculture import SHOPS, MARKET_PARAMS

# $/unit at the revenue-maximising steady sale rate, from code/a_plan.py
SOLO = {"WHEAT": 19.8, "CARROT": 13.7, "TOMATO": 26.2, "STRAWBERRY": 159.9,
        "MELON": 188.4, "EGG": 39.0, "MILK": 179.8, "WOOL": 190.9, "FERTILIZER": 14.3}
RIVAL = {"WHEAT": 19.1, "CARROT": 4.0, "TOMATO": 26.5, "STRAWBERRY": 162.1,
         "MELON": 190.1, "EGG": 37.7, "MILK": 182.2, "WOOL": 193.5, "FERTILIZER": 7.7}
# and the season volume that rate implies
VOL = {"WHEAT": 1848, "CARROT": 1056, "TOMATO": 604, "STRAWBERRY": 300, "MELON": 171,
       "EGG": 1848, "MILK": 261, "WOOL": 227, "FERTILIZER": 1848}

# units per tile-day, watering daily, fertilising through the bonus window
CROP = {  # (units, tile-days occupied, seed cost)
    "WHEAT":      (6, 5,  10), "CARROT": (4, 4, 20), "TOMATO": (8, 12, 50),
    "STRAWBERRY": (8, 17, 100), "MELON": (6, 9,  80),
}
ANIMAL = {  # (product, units/day with CARE, cost, days to first yield)
    "GOOSE": ("EGG", 2.0, 300, 4), "COW": ("MILK", 1.5, 400, 8),
    "SHEEP": ("WOOL", 4.0 / 3.0, 500, 6),
}

print("=== $ per tile-day ===")
print(f"{'':14s} {'units/tile-day':>14s} {'solo':>9s} {'w/ rival':>9s} "
      f"{'tiles the market feeds':>24s}")
rows = []
for c, (u, d, seed) in CROP.items():
    rate = u / float(d)
    solo = rate * SOLO[c] - seed / float(d)
    riv = rate * RIVAL[c] - seed / float(d)
    tiles = VOL[c] / rate / 25.0
    rows.append((solo, c, rate, solo, riv, tiles))
for a, (prod, rate, cost, first) in ANIMAL.items():
    # an animal also makes 1 fertilizer/day free and eats 1 wheat/day
    solo = rate * SOLO[prod] + SOLO["FERTILIZER"] - SOLO["WHEAT"] - cost / 22.0
    riv = rate * RIVAL[prod] + RIVAL["FERTILIZER"] - RIVAL["WHEAT"] - cost / 22.0
    tiles = VOL[prod] / rate / 22.0
    rows.append((solo, a, rate, solo, riv, tiles))
for _k, name, rate, solo, riv, tiles in sorted(rows, reverse=True):
    print(f"{name:14s} {rate:14.2f} {solo:9.0f} {riv:9.0f} {tiles:24.0f}")

print("""
Read the last column with the third: a cow is worth ~10x a wheat tile per day,
but the milk market only feeds about eight of them.  No single line reaches the
~150k reference on its own -- the plan has to run every row at once, each capped
where its own curve gives out.  That is why main.py caps tiles per crop and
prices every extra animal at the margin instead of filling the board with the
best one.""")

print("\n=== does the town alone push carrot / tomato / egg past the hinge? ===")
names = sorted(SHOPS)
ACTIVE = [27, 24, 21, 18, 15, 12, 9, 6]
rng = random.Random(0)
hits = collections.Counter()
N = 100000
for _ in range(N):
    draw = [rng.choice(names) for _ in ACTIVE]
    d = collections.Counter()
    for shop, act in zip(draw, ACTIVE):
        prods = SHOPS[shop]
        mult = 2 if len(prods) == 1 else 1
        for p in prods:
            d[p] += mult * act * 6
    for p in ("CARROT", "TOMATO", "EGG"):
        if d[p] + 30 > MARKET_PARAMS[p]["T"]:
            hits[p] += 1
for p in ("CARROT", "TOMATO", "EGG"):
    print(f"  {p:8s} T={MARKET_PARAMS[p]['T']:4d}   town drain exceeds T in "
          f"{hits[p]/N:5.1%} of seasons")
print("""
...but only if nobody sells into it.  Every unit we sell pushes inventory back
up, so crossing the knee means deliberately *not* selling the crop the town is
starving for.  Since the convex branch is where the money is, main.py's reserve
prices are what keep the option open: it stops selling carrot below $24 and
tomato below $38 rather than flattening the curve for a few dollars a unit.""")
