"""Score a candidate against the current opponent pool, both seats, many seeds.

    python tools/eval_field.py <candidate.py> [--seeds N] [--json out.json]
    python tools/eval_field.py --round-robin            # pool against itself

The arena ranks by a rating built from wins against a live field, so the local
question worth asking is the same shape: how often does this candidate out-bank the
current public field, from either seat. Absolute money against a weak built-in has
almost no resolution — six competent agents sit within 10% of each other on it while
their head-to-head win rates span 60 points — so it is reported only as a crash check.

The pool is scoring material and goes stale: re-pull it with refresh_opponents.py
before trusting a number, and read opponents/MANIFEST.json for when it was taken.
"""
from __future__ import annotations
import argparse, itertools, json, statistics, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))


def _game(task):
    import engine
    a_path, b_path, seed = task
    a = engine.builtin(a_path[9:]) if a_path.startswith("builtin::") else engine.load_agent(a_path)
    b = engine.builtin(b_path[9:]) if b_path.startswith("builtin::") else engine.load_agent(b_path)
    ba, bb = engine.play(a, b, seed)
    return a_path, b_path, seed, ba, bb


def pool() -> list[Path]:
    return sorted(p for p in (REPO / "opponents").glob("*.py"))


def run(tasks, workers):
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_game, tasks, chunksize=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate", nargs="?")
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--json", default="")
    ap.add_argument("--round-robin", action="store_true")
    args = ap.parse_args()

    seeds = list(range(1001, 1001 + args.seeds))
    opps = pool()
    if not opps:
        raise SystemExit("opponent pool is empty — run tools/refresh_opponents.py")

    if args.round_robin:
        subjects = [str(p) for p in opps]
        tasks = [(x, y, s) for x, y in itertools.permutations(subjects, 2) for s in seeds]
    else:
        if not args.candidate:
            raise SystemExit("give a candidate, or --round-robin")
        c = str(Path(args.candidate).resolve())
        subjects = [c]
        tasks = [(c, str(o), s) for o in opps for s in seeds]
        tasks += [(str(o), c, s) for o in opps for s in seeds]
        tasks += [(c, "builtin::starter", s) for s in seeds]

    rows = run(tasks, args.workers)

    wins = {s: 0 for s in subjects}; games = {s: 0 for s in subjects}
    margins = {s: [] for s in subjects}; crash = {s: 0 for s in subjects}
    starter_bank = []
    for a, b, seed, ba, bb in rows:
        if b == "builtin::starter":
            starter_bank.append(ba); continue
        for me, opp, mine, theirs in ((a, b, ba, bb), (b, a, bb, ba)):
            if me not in wins:
                continue
            games[me] += 1; wins[me] += mine > theirs; margins[me].append(mine - theirs)
            crash[me] += mine <= 0

    out = {"seeds": seeds, "pool": [p.name for p in opps], "subjects": {}}
    for s in sorted(subjects, key=lambda s: -(wins[s] / max(games[s], 1))):
        wr = wins[s] / max(games[s], 1)
        rec = {"win_rate": wr, "games": games[s],
               "margin_mean": statistics.mean(margins[s]) if margins[s] else 0.0,
               "margin_min": min(margins[s]) if margins[s] else 0.0,
               "zero_bank_games": crash[s]}
        if starter_bank and s == subjects[0] and not args.round_robin:
            rec["bank_vs_starter_mean"] = statistics.mean(starter_bank)
        out["subjects"][Path(s).name] = rec
        print(f"  {Path(s).name[:46]:46s} win {wr*100:5.1f}%  "
              f"margin {rec['margin_mean']:+10.0f}  min {rec['margin_min']:+10.0f}  "
              f"games {games[s]}" + (f"  zero-bank {crash[s]}" if crash[s] else ""))
    if starter_bank and not args.round_robin:
        print(f"\n  crash check: mean bank vs starter = {statistics.mean(starter_bank):,.0f} "
              f"({sum(1 for b in starter_bank if b<=0)}/{len(starter_bank)} zero-bank)")
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2) + "\n")
        print(f"  wrote {args.json}")


if __name__ == "__main__":
    main()
