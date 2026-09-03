"""Measure the town: which shops unlock, how much they drain, where prices land.

Both seats PASS, so market inventory moves only from town consumption.
"""
import sys, statistics, collections
sys.path.insert(0, "tools")
import kagsim

PRODUCTS = ["WHEAT","CARROT","TOMATO","STRAWBERRY","MELON","EGG","MILK","WOOL","FERTILIZER"]

def run(seed):
    g = kagsim.Game(seed)
    passer = {"farmer": ["PASS"], "hands": [], "market": []}
    trace = []
    while not g.done:
        o = g.observe(0)
        if o["hour"] == 0:
            trace.append((o["day"], dict(o["market"]["inventory"]), dict(o["market"]["prices"]),
                          list(o["town"]["unlocked_shops"])))
        g.step(passer, passer)
    o = g.observe(0)
    trace.append((30, dict(o["market"]["inventory"]), dict(o["market"]["prices"]),
                  list(o["town"]["unlocked_shops"])))
    return trace

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
drains = collections.defaultdict(list)
finalp = collections.defaultdict(list)
shopcount = collections.Counter()
for seed in range(1, N+1):
    tr = run(seed)
    d, inv, pr, shops = tr[-1]
    for p in PRODUCTS:
        drains[p].append(10000 - inv[p])
        finalp[p].append(pr[p])
    for s in shops:
        shopcount[s] += 1
    if seed <= 3:
        print(f"seed {seed} shops={shops}")
        for (day, inv, pr, sh) in tr[::5]:
            print(f"   d{day:2d} " + " ".join(f"{p[:4]}:{10000-inv[p]:4d}/${pr[p]:3d}" for p in PRODUCTS))

print(f"\n=== {N} seeds, PASS vs PASS: town drain by end of season (units removed from I0) ===")
print(f"{'product':12s} {'mean':>7s} {'min':>6s} {'max':>6s}   {'price mean':>10s} {'min':>5s} {'max':>5s}")
for p in PRODUCTS:
    d = drains[p]; f = finalp[p]
    print(f"{p:12s} {statistics.mean(d):7.1f} {min(d):6d} {max(d):6d}   {statistics.mean(f):10.1f} {min(f):5d} {max(f):5d}")
print("\nshop instances drawn:", dict(shopcount.most_common()))
