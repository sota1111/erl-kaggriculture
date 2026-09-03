"""Parameter sweep for the tunables main.py could not settle without episodes.

Needs episodes enabled. Every constant swept here is read at call time, so a
worker can load main.py and override it in place; main.py itself is untouched.

    .venv/bin/python code/sweep.py --seeds 8 --workers 12
    .venv/bin/python code/sweep.py --grid opening --seeds 12

Scored on mean bank over `seeds` seeds x both seats vs `starter`, and again in
self-play (which is the only local check that a strategy survives a strong,
market-sharing rival). Report both: a setting that lifts the starter number but
sinks the self-play number is buying bank off an opponent that does not exist.
"""
from __future__ import annotations
import argparse, importlib.util, itertools, statistics, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

GRIDS = {
    # How much rival volume to assume when pricing our own production. 0.0 is
    # "the opponent does not exist"; 1.0 is "they match me tile for tile".
    "rival": {"OPP_MIRROR": [0.0, 0.3, 0.6, 0.9]},
    # Hiring: fib(n) per hand per day. 12 sits just under the knee, but the knee
    # only matters if there is work for the hands.
    "labour": {"MAX_HANDS": [8, 10, 12, 14], "DIST_WEIGHT": [1.6, 2.4, 3.4]},
    # Opening tempo: how strongly early cash is preferred over a slow crop.
    "opening": {"MAX_ANIMALS": [30, 38, 46], "DROP_THRESHOLD": [10, 16, 24]},
    # Sale pacing: small parcels let town consumption refill the scarcity gap
    # between our sales; large parcels get the whole line out before a rival dumps.
    "selling": {"_SELL_SCALE": [0.5, 1.0, 2.0, 4.0]},
}


def _load(overrides):
    spec = importlib.util.spec_from_file_location("swept", str(ROOT / "main.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k, v in overrides.items():
        if k == "_SELL_SCALE":
            mod.SELL_CAP = {i: max(1, int(round(c * v)))
                            for i, c in mod.SELL_CAP.items()}
        else:
            setattr(mod, k, v)
    return mod.agent


def _one(task):
    import engine
    overrides, opp, seed, seat = task
    me = _load(overrides)
    other = (engine.builtin(opp) if opp in ("starter", "random", "pass")
             else _load(overrides))
    x, y = (engine.play(me, other, seed) if seat == 0
            else engine.play(other, me, seed))
    mine, theirs = (x, y) if seat == 0 else (y, x)
    return tuple(sorted(overrides.items())), opp, mine, mine - theirs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", default="rival", choices=sorted(GRIDS))
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    grid = GRIDS[args.grid]
    keys = sorted(grid)
    combos = [dict(zip(keys, vals)) for vals in itertools.product(*(grid[k] for k in keys))]
    tasks = [(c, opp, s, seat)
             for c in combos for opp in ("starter", "SELF")
             for s in range(1, args.seeds + 1) for seat in (0, 1)]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(_one, tasks, chunksize=2))

    print(f"grid={args.grid}  seeds={args.seeds}  episodes={len(tasks)}")
    print(f"{'setting':<44} {'vs starter bank':>16} {'margin':>10} {'self bank':>11}")
    out = []
    for c in combos:
        key = tuple(sorted(c.items()))
        st = [r for r in rows if r[0] == key and r[1] == "starter"]
        sf = [r for r in rows if r[0] == key and r[1] == "SELF"]
        bank = statistics.mean(r[2] for r in st) if st else 0.0
        marg = statistics.mean(r[3] for r in st) if st else 0.0
        sbank = statistics.mean(r[2] for r in sf) if sf else 0.0
        out.append((bank, c, marg, sbank))
    for bank, c, marg, sbank in sorted(out, reverse=True):
        label = ", ".join(f"{k}={v}" for k, v in sorted(c.items()))
        print(f"{label:<44} {bank:>16,.0f} {marg:>+10,.0f} {sbank:>11,.0f}")


if __name__ == "__main__":
    main()
