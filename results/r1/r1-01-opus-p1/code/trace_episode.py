"""Run one episode and dump per-day diagnostics for this agent.

Needs episodes enabled (tools/engine.py raises SimulationDisabled otherwise).

    .venv/bin/python code/trace_episode.py --seed 1 --seat 0 --opp starter

Prints, per day: bank, tile census, hands hired, market prices, and the split of
unit-actions actually issued. The action split is the one number that says
whether labour is the binding constraint: if MOVE dominates, the layout or the
distance weight is wrong; if PASS appears, we are paying for hands we cannot use.
"""
from __future__ import annotations
import argparse, collections, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import engine  # noqa: E402

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seat", type=int, default=0, choices=(0, 1))
    ap.add_argument("--opp", default="starter")
    ap.add_argument("--candidate", default=str(ROOT / "main.py"))
    args = ap.parse_args()

    inner = engine.load_agent(args.candidate)
    days = collections.defaultdict(lambda: collections.Counter())
    snap = {}

    def wrapped(obs):
        act = inner(obs)
        day = obs.get("day", 0)
        c = days[day]
        for a in [act["farmer"]] + list(act["hands"]):
            c["MOVE" if a[0] in MOVES else a[0]] += 1
        for o in act["market"]:
            c["mkt:" + o[0]] += 1
        p = obs.get("player", 0)
        farm = obs["farms"][p]
        if day not in snap or obs.get("hour", 0) == 23:
            census = collections.Counter()
            for row in farm["tiles"]:
                for t in row:
                    if t is None:
                        census["empty"] += 1
                    elif t == "LOCKED":
                        census["locked"] += 1
                    elif t.get("kind") == "PLANT":
                        census[t["crop"].lower()] += 1
                    elif t.get("kind") == "WEED":
                        census["WEED"] += 1
                    elif t.get("animal"):
                        census[t["animal"].lower()] += 1
                    else:
                        census["struct"] += 1
            snap[day] = (farm["money"], census, len(farm["hands"]),
                         dict(obs["market"]["prices"]),
                         list(obs["town"]["unlocked_shops"]))
        return act

    opp = (engine.builtin(args.opp) if args.opp in ("starter", "random", "pass")
           else engine.load_agent(args.opp))
    a, b = ((wrapped, opp) if args.seat == 0 else (opp, wrapped))
    r = engine.play(a, b, args.seed)
    mine, theirs = (r[0], r[1]) if args.seat == 0 else (r[1], r[0])

    print(f"backend={engine.backend()} seed={args.seed} seat={args.seat} "
          f"opp={args.opp}")
    print(f"{'day':>3} {'bank':>9} {'hands':>5}  tiles")
    for day in sorted(snap):
        money, census, hands, prices, shops = snap[day]
        tiles = " ".join(f"{k}:{v}" for k, v in sorted(census.items())
                         if k not in ("locked",) and v)
        print(f"{day:>3} {money:>9,.0f} {hands:>5}  {tiles}")
    print("\nprices at end of season:")
    _, _, _, prices, shops = snap[max(snap)]
    print("  " + "  ".join(f"{k}=${v}" for k, v in prices.items()))
    print(f"  shops: {shops}")
    print("\naction split per day (top ops):")
    for day in sorted(days):
        c = days[day]
        tot = sum(v for k, v in c.items() if not k.startswith("mkt:"))
        top = ", ".join(f"{k} {v}" for k, v in c.most_common(7)
                        if not k.startswith("mkt:"))
        print(f"{day:>3} n={tot:<4} {top}")
    print(f"\nFINAL  mine={mine:,.0f}  theirs={theirs:,.0f}  "
          f"margin={mine - theirs:+,.0f}")


if __name__ == "__main__":
    main()
