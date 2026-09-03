"""How much of each product is it worth producing?

Sales are not a one-shot dump: the town drains the market every day, so the
price recovers between sales.  This models the actual time path -- for each
product, sell s units/day from day `start` to day 29 while the town removes its
(expected) daily quota -- and reports the revenue-maximising s.

`--rival R` makes the opponent dump R x my rate into the same market, which is
the only way to see how much of the headline number is really mine.
"""
import sys, argparse
sys.path.insert(0, ".venv/lib/python3.12/site-packages")
from kaggle_environments.envs.kaggriculture.kaggriculture import market_price, PRODUCTS

# expected units the town removes per day, before day 24 it ramps: shops unlock
# on days 3,6,...,24, so the rate at day d is (center + 6*mult*E[shops up]).
PER_SHOP_RATE = {   # expected units/day removed by ONE unlocked shop instance
    "WHEAT": 6 * 5 / 8, "CARROT": 6 * 3 / 8, "TOMATO": 6 * 2 / 8,
    "STRAWBERRY": 6 * 4 / 8, "MELON": 0.0, "EGG": 6 * 2 / 8,
    "MILK": 6 * 3 / 8, "WOOL": 6 * 2 / 8, "FERTILIZER": 0.0,
}
CENTER = {p: (0 if p == "FERTILIZER" else 1) for p in PRODUCTS}


def shops_up(day):
    return min(8, max(0, day // 3))


def revenue(item, rate, start=6, rival=0.0, end=30):
    """Sell `rate` units/day from `start`..`end-1`; return (revenue, units, last price)."""
    inv, rev, sold, carry, rcarry = 10000, 0.0, 0, 0.0, 0.0
    for day in range(end):
        inv -= CENTER[item] + PER_SHOP_RATE[item] * shops_up(day)
        if day < start:
            continue
        carry += rate
        rcarry += rate * rival
        n = int(carry); carry -= n
        rn = int(rcarry); rcarry -= rn
        # both sides sell into the same book, interleaved one unit at a time
        while n > 0 or rn > 0:
            p = market_price(item, int(round(inv)))
            if n > 0:
                rev += p; sold += 1; n -= 1
                if p > 1: inv += 1
            if rn > 0:
                rn -= 1
                if market_price(item, int(round(inv))) > 1: inv += 1
    return rev, sold, market_price(item, int(round(inv)))


ap = argparse.ArgumentParser()
ap.add_argument("--rival", type=float, default=0.0)
ap.add_argument("--start", type=int, default=6)
a = ap.parse_args()

print(f"selling steadily from day {a.start} to 29, opponent dumping {a.rival:.0%} of my rate\n")
print(f"{'product':12s} {'best/day':>8s} {'units':>6s} {'revenue':>9s} {'$/unit':>7s} {'endprice':>8s}"
      f"   {'rev at 1/2 rate':>15s} {'rev at 2x rate':>14s}")
tot = 0.0
best_rate = {}
for p in PRODUCTS:
    cand = []
    r = 0.25
    while r <= 80:
        cand.append((revenue(p, r, a.start, a.rival)[0], r))
        r *= 1.15
    rev, r = max(cand)
    best_rate[p] = r
    _, units, endp = revenue(p, r, a.start, a.rival)
    half = revenue(p, r / 2, a.start, a.rival)[0]
    dbl = revenue(p, r * 2, a.start, a.rival)[0]
    tot += rev
    print(f"{p:12s} {r:8.2f} {units:6d} {rev:9,.0f} {rev/max(units,1):7.1f} {endp:8d}"
          f"   {half:15,.0f} {dbl:14,.0f}")
print(f"\ntotal if every product is produced at its own optimum: {tot:,.0f}")
print("optimal daily sale rates:", {k: round(v, 1) for k, v in best_rate.items()})
