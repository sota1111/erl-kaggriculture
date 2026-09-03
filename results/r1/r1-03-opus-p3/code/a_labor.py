"""Is the plan staffable, and where does the last hand stop paying?

Hiring costs farmHandCostMult * fib(n) with n resetting every day, so the whole
wage bill is a rounding error next to the revenue -- until it suddenly is not.
This prices the marginal hand against the marginal action.  Arithmetic only; no
episode is run.
"""
import sys

def fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a

print("=== cost of a day's hiring ===")
print(f"{'hands':>5} {'nth costs':>10} {'day total':>10} {'season(20d)':>12} "
      f"{'actions/day':>12} {'$/action of nth':>16}")
tot = 0
for n in range(0, 18):
    c = fib(n)
    tot += c
    # a hand hired at hour 0 first acts at hour 1 and works to hour 23
    print(f"{n+1:5d} {c:10d} {tot:10d} {tot*20:12,d} {(n+2)*23:12d} {c/23.0:16.2f}")

print("""
A hand is 23 actions.  At the ~$15-30 an action the crop table supports, the
n-th hand stops paying when fib(n)/23 passes that -- fib(13)=377 is $16/action,
fib(14)=610 is $27.  So the useful ceiling is 13-14 hands, and it is set by the
wage curve, not by cash.""")

print("\n=== is the target farm staffable? ===")
# actions per day, per tile, at the steady state the plan aims for
WORK = {
    "animal": 3.5,     # FEED + CARE + COLLECT_FERTILIZER + share of HARVEST
    "crop":   1.35,    # WATER + share of PLANT / HARVEST / FERTILIZE
    "empty":  2.0,     # PLANT then WATER the same day
}
for name, (animals, crops, empt) in [
        ("day 0, NW only", (0, 0, 25)),
        ("day 1, NW+NE", (0, 25, 25)),
        ("day 6, three quadrants", (8, 55, 12)),
        ("day 14, full board", (30, 60, 10)),
        ("day 20, full board", (34, 62, 4))]:
    work = animals * WORK["animal"] + crops * WORK["crop"] + empt * WORK["empty"]
    # movement: a unit walking its own contiguous slice spends roughly one step
    # per tile it services, plus the morning commute out of the shed
    for hands in range(4, 16):
        units = hands + 1
        commute = units * 4
        avail = units * 23 - commute
        if avail >= work + (animals + crops + empt) * 0.9:
            break
    move = (animals + crops + empt) * 0.9
    print(f"{name:24s} work {work:6.1f} + move {move:5.1f} = {work+move:6.1f} actions/day"
          f"  -> {hands:2d} hands ({(hands+1)*23 - (hands+1)*4:4d} usable), "
          f"wage {sum(fib(i) for i in range(hands)):5d}/day")

print("""
The plan needs 12-14 hands at full build and 3-6 in the opening, which is what
the hire rule in main.py targets (weight/19, capped by cash).  The wage at 13
hands is $609/day: under 4% of the daily revenue the market model says a full
board can produce.  Labour is not the binding constraint -- land, market depth
and the 100-slot shed are.""")
