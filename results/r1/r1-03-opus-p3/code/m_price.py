"""Price curve + dump-revenue table, computed from the shipped MARKET_PARAMS
and then CHECKED against the live engine by actually selling into it."""
import math, sys
sys.path.insert(0, "tools")
from kaggle_environments.envs.kaggriculture.kaggriculture import MARKET_PARAMS, market_price, PRODUCTS

print("=== price(I0 + x): what happens as I dump x units ===")
xs = [0,25,50,100,150,200,300,400,600,900,1500]
print(f"{'item':11s} " + " ".join(f"{x:>5d}" for x in xs))
for p in PRODUCTS:
    print(f"{p:11s} " + " ".join(f"{market_price(p,10000+x):>5d}" for x in xs))

print("\n=== price(I0 - x): what the town's drain does ===")
for p in PRODUCTS:
    print(f"{p:11s} " + " ".join(f"{market_price(p,10000-x):>5d}" for x in xs))

print("\n=== cumulative revenue R(N) of dumping N units into an undrained market ===")
Ns = [25,50,100,150,200,300,500,800]
print(f"{'item':11s} " + " ".join(f"{n:>8d}" for n in Ns))
for p in PRODUCTS:
    rev, out, inv = 0, [], 10000
    for i in range(1, max(Ns)+1):
        pr = market_price(p, inv)
        rev += pr
        if pr > 1: inv += 1
        if i in Ns: out.append(rev)
    print(f"{p:11s} " + " ".join(f"{r:>8,d}" for r in out))

print("\n=== marginal price of the Nth unit dumped (undrained market) ===")
print(f"{'item':11s} " + " ".join(f"{n:>8d}" for n in Ns))
for p in PRODUCTS:
    out, inv = [], 10000
    for i in range(1, max(Ns)+1):
        pr = market_price(p, inv)
        if pr > 1: inv += 1
        if i in Ns: out.append(pr)
    print(f"{p:11s} " + " ".join(f"{r:>8,d}" for r in out))
