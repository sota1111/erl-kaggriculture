"""Town demand, computed from the rules (no episode needed).

Shops unlock at end of day 2,5,8,...  -> active from day 3,6,...,24 (8 instances,
the cap). Each instance consumes 1 of each demanded product every 4 turns = 6/day,
doubled for single-product shops. The town centre eats 1 of every non-fertilizer
product once a day for all 30 days.

Shop identity is a uniform draw with replacement, so the per-product drain is a
random variable with a large spread over only 8 draws. We report its distribution.
"""
import random, statistics, collections, sys
sys.path.insert(0, ".venv/lib/python3.12/site-packages")
from kaggle_environments.envs.kaggriculture.kaggriculture import SHOPS, PRODUCTS, TOWN_CENTER_PRODUCTS

SEASON = 30
UNLOCK_DAYS = [3 * k for k in range(1, 9)]          # 3,6,...,24
ACTIVE_DAYS = [SEASON - d for d in UNLOCK_DAYS]     # 27,24,...,6
TICKS_PER_DAY = 24 // 4

print("shop unlock days:", UNLOCK_DAYS)
print("active days each:", ACTIVE_DAYS, " total shop-instance-days:", sum(ACTIVE_DAYS))

names = sorted(SHOPS)
def drain_of(draw):
    d = collections.Counter()
    for item in TOWN_CENTER_PRODUCTS:
        d[item] += SEASON                       # town centre, flat
    for shop, act in zip(draw, ACTIVE_DAYS):
        prods = SHOPS[shop]
        mult = 2 if len(prods) == 1 else 1
        for p in prods:
            d[p] += mult * act * TICKS_PER_DAY
    return d

rng = random.Random(0)
samples = collections.defaultdict(list)
for _ in range(200000):
    d = drain_of([rng.choice(names) for _ in UNLOCK_DAYS])
    for p in PRODUCTS:
        samples[p].append(d[p])

print(f"\nseason-long town drain (units removed from I0), 200k random shop draws")
print(f"{'product':12s} {'mean':>7s} {'p10':>6s} {'p50':>6s} {'p90':>6s} {'max':>6s}   shops that demand it")
for p in PRODUCTS:
    s = sorted(samples[p])
    q = lambda f: s[int(f * (len(s) - 1))]
    who = [n for n in names if p in SHOPS[n]]
    print(f"{p:12s} {statistics.mean(s):7.0f} {q(.1):6d} {q(.5):6d} {q(.9):6d} {max(s):6d}   {','.join(w.lower() for w in who) or '-'}")

# per-day drain rate once all 8 shops are up
print("\nper-day drain once all 8 instances are unlocked (day 24+), mean over draws:")
for p in PRODUCTS:
    per_shop = sum(1 for n in names if p in SHOPS[n] and len(SHOPS[n]) > 1) / 8.0
    per_shop += sum(2 for n in names if p in SHOPS[n] and len(SHOPS[n]) == 1) / 8.0
    center = 1 if p in TOWN_CENTER_PRODUCTS else 0
    print(f"  {p:12s} {8 * per_shop * TICKS_PER_DAY + center:6.1f} /day")
