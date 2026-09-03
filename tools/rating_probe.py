"""Sample a submission's rating against the episodes it has played.

    python tools/rating_probe.py [SUBMISSION_ID] [--append results/baseline/<file>.md]

A rating moves per EPISODE, not per hour, and the ladder feeds different agents games
at very different rates, so wall-clock is the wrong unit for "has it settled yet".
Sample the pair (score, episodes), take the drift per episode between samples, and
treat the number as readable once the drift is small AND its sign has flipped at
least once. Even then it is not fixed: the rating measures you against a field that
keeps moving, so an unchanged agent can drift by a few hundred points over time.
"""
from __future__ import annotations
import argparse, csv, io, subprocess, sys
from datetime import datetime, timezone


def latest_submission() -> tuple[str, float]:
    out = subprocess.run(["kaggle", "competitions", "submissions", "-c", "kaggriculture", "--csv"],
                         capture_output=True, text=True, check=True).stdout
    r = next(csv.DictReader(io.StringIO(out)))
    return r["ref"], float(r["publicScore"] or 0)


def score_of(sub_id: str) -> float:
    out = subprocess.run(["kaggle", "competitions", "submissions", "-c", "kaggriculture", "--csv"],
                         capture_output=True, text=True, check=True).stdout
    for r in csv.DictReader(io.StringIO(out)):
        if r["ref"] == str(sub_id):
            return float(r["publicScore"] or 0)
    raise SystemExit(f"submission {sub_id} not found")


def episodes_of(sub_id: str) -> int:
    out = subprocess.run(["kaggle", "competitions", "episodes", str(sub_id), "-v"],
                         capture_output=True, text=True, check=True).stdout
    return max(len(out.splitlines()) - 1, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("submission", nargs="?")
    ap.add_argument("--append", default="")
    args = ap.parse_args()

    sub = args.submission or latest_submission()[0]
    score, eps = score_of(sub), episodes_of(sub)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    line = f"| {stamp} | {eps} | {score:.1f} |"
    print(f"submission {sub}: {eps} episodes, score {score:.1f}")
    print(line)
    if args.append:
        with open(args.append, "a") as fh:
            fh.write(line + "\n")
        print(f"appended to {args.append}")


if __name__ == "__main__":
    main()
