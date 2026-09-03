"""Snapshot the public leaderboard and compute where the medal lines sit.

    python tools/lb_snapshot.py                      # fetch live, print, save CSV under results/lb/
    python tools/lb_snapshot.py --csv <file>         # re-analyse a saved snapshot
    python tools/lb_snapshot.py --score 2543.4       # also report where a score would land

Why this exists: the arena score is a *rating*, not money, and the medal lines are
percentiles of a team count that moves every day. A candidate is only worth
promoting relative to the line it has to clear, so the line has to be measured,
not remembered.

Kaggle medal thresholds for a competition with >1000 teams:
  bronze = top 10%   silver = top 5%   gold = top 10 + 0.2%
"""
import argparse, csv, os, subprocess, sys, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMP = "kaggriculture"


def fetch(dest_dir: Path) -> Path:
    """Download the live public leaderboard via the Kaggle CLI, return the CSV path."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["kaggle", "competitions", "leaderboard", "-c", COMP, "--download", "-p", tmp, "-q"],
            check=True,
        )
        zips = list(Path(tmp).glob("*.zip"))
        if not zips:
            raise SystemExit("kaggle CLI returned no leaderboard archive")
        with zipfile.ZipFile(zips[0]) as z:
            name = z.namelist()[0]
            data = z.read(name)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{datetime.now(timezone.utc):%Y-%m-%d}_public_leaderboard.csv"
    out.write_bytes(data)
    return out


def thresholds(scores):
    n = len(scores)
    return {
        "gold": (10 + int(n * 0.002), scores[10 + int(n * 0.002) - 1]),
        "silver": (int(n * 0.05), scores[int(n * 0.05) - 1]),
        "bronze": (int(n * 0.10), scores[int(n * 0.10) - 1]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="", help="analyse a saved snapshot instead of fetching")
    ap.add_argument("--score", type=float, action="append", default=[],
                    help="report the rank this score would take (repeatable)")
    ap.add_argument("--team", default=os.environ.get("KAGGLE_USERNAME", ""),
                    help="team name to locate on the board")
    args = ap.parse_args()

    path = Path(args.csv) if args.csv else fetch(REPO / "results" / "lb")
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    scores = [float(r["Score"]) for r in rows]
    n = len(scores)

    print(f"snapshot: {path.name}   teams: {n}")
    for medal, (rank, cut) in thresholds(scores).items():
        print(f"  {medal:6s}  rank <= {rank:5d}   score >= {cut:.1f}")

    for pct in (1, 2, 5, 10, 20, 50):
        k = max(1, int(n * pct / 100))
        print(f"  top {pct:3d}%  rank {k:5d}   score {scores[k - 1]:.1f}")

    for s in args.score:
        rank = sum(1 for x in scores if x > s) + 1
        t = thresholds(scores)
        medal = ("gold" if rank <= t["gold"][0] else "silver" if rank <= t["silver"][0]
                 else "bronze" if rank <= t["bronze"][0] else "none")
        print(f"  score {s:8.1f} -> rank {rank:5d}/{n} (top {rank / n * 100:.2f}%)  medal: {medal}")

    if args.team:
        for r in rows:
            if r["TeamName"].strip().lower() == args.team.strip().lower():
                print(f"  me: rank {r['Rank']}  score {r['Score']}  last submission {r['LastSubmissionDate']}")
                break
        else:
            print(f"  me: team '{args.team}' not on this snapshot")


if __name__ == "__main__":
    main()
