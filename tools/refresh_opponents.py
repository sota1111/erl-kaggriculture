"""Rebuild the opponent pool from the CURRENT public kernels.

The pool is scoring material, never solution material: agents developed in this
repository do not see it (docs/round1_plan.md ss5). It goes stale fast — the meta
turned over inside three weeks — so the pool carries the date it was pulled and is
meant to be re-pulled, not inherited.

    python tools/refresh_opponents.py --top 10          # pull and extract
    python tools/refresh_opponents.py --list            # just show what is out there

Each kernel is recorded with its ref, author, vote count, last run time, the sha256
of the extracted agent, and the author's leaderboard rating on the day of the pull.
That last column is a proxy and a weak one: it rates the author's CURRENT submission,
not this frozen kernel.
"""
from __future__ import annotations
import argparse, csv, json, re, subprocess, sys, tempfile, hashlib
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
POOL = REPO / "opponents"
COMP = "kaggriculture"


def kernels(limit: int, sort: str = "voteCount"):
    out = subprocess.run(
        ["kaggle", "kernels", "list", "--competition", COMP, "--sort-by", sort,
         "--page-size", str(max(limit, 20)), "--csv"],
        capture_output=True, text=True, check=True).stdout
    rows = list(csv.DictReader(out.splitlines()))
    return rows[:limit]


def extract_agent(nb_path: Path) -> str | None:
    """Recover the agent a notebook packages, by running its packaging cells safely.

    Kernels write main.py four different ways (writefile magic, agentfile magic,
    write_text of a source string, base64/zlib blobs), so rather than pattern-match
    each, execute the candidate cells in a sandbox and take the main.py they produce.
    Falls back to the cell text when a cell simply defines agent() inline.
    """
    nb = json.loads(nb_path.read_text())
    cells = ["".join(c["source"]) for c in nb.get("cells", []) if c.get("cell_type") == "code"]
    interesting = sorted((c for c in cells if "def agent" in c or "main.py" in c),
                         key=len, reverse=True)[:4]
    for src in interesting:
        with tempfile.TemporaryDirectory() as work:
            cellfile = Path(work) / "_src.py"
            cellfile.write_text(src)
            out = subprocess.run(
                [sys.executable, str(REPO / "tools" / "_sandbox_extract.py"), str(cellfile), work],
                capture_output=True, text=True, timeout=300)
            path = out.stdout.strip()
            if path and Path(path).is_file():
                return Path(path).read_text()
    for src in interesting:
        m = re.match(r"^\s*%%(?:writefile\s+\S*main\.py|agentfile\S*)\s*\n", src)
        body = src[m.end():] if m else src
        if "def agent" in body and "get_ipython" not in body:
            return body
    return None


def usable(code: str) -> str | None:
    """An opponent counts only if it loads and survives an episode. Runs in a
    subprocess with a temp cwd: loading a stranger's agent executes its module body."""
    with tempfile.TemporaryDirectory() as work:
        agent = Path(work) / "cand.py"
        agent.write_text(code)
        probe = Path(work) / "_probe.py"
        probe.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(REPO / 'tools')!r})\n"
            "import engine\n"
            f"a = engine.load_agent({str(agent)!r})\n"
            "print(engine.play(a, engine.builtin('starter'), 11)[0])\n")
        r = subprocess.run([sys.executable, str(probe)], capture_output=True,
                           text=True, cwd=work, timeout=600)
        if r.returncode != 0:
            return (r.stderr.strip().splitlines() or ["failed"])[-1][:120]
        try:
            return None if float(r.stdout.strip().splitlines()[-1]) > 0 else "banked nothing"
        except Exception:
            return "no bank on stdout"


def lb_ratings() -> dict:
    """Author username -> current leaderboard rating, from today's board."""
    snaps = sorted((REPO / "results" / "lb").glob("*_public_leaderboard.csv"))
    if not snaps:
        return {}
    out = {}
    for r in csv.DictReader(snaps[-1].open(encoding="utf-8-sig")):
        for u in (r.get("TeamMemberUserNames") or "").split(","):
            if u.strip():
                out[u.strip().lower()] = float(r["Score"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--sort", default="voteCount", choices=("voteCount", "dateRun"))
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    rows = kernels(args.top, args.sort)
    if args.list:
        for r in rows:
            print(f"{r['totalVotes']:>5} votes  {r['lastRunTime'][:10]}  {r['ref']}")
        return

    ratings = lb_ratings()
    POOL.mkdir(exist_ok=True)
    manifest = []
    for r in rows:
        ref = r["ref"]
        author = ref.split("/")[0]
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["kaggle", "kernels", "pull", ref, "-p", tmp, "-m"],
                           capture_output=True, check=False)
            nbs = list(Path(tmp).glob("*.ipynb"))
            if not nbs:
                print(f"  skip {ref}: no notebook"); continue
            code = extract_agent(nbs[0])
        if not code:
            print(f"  skip {ref}: no agent source found"); continue
        why = usable(code)
        if why:
            print(f"  skip {ref}: does not run ({why})"); continue
        name = re.sub(r"[^a-z0-9]+", "_", ref.split("/")[1].lower()).strip("_")[:48]
        dest = POOL / f"{name}.py"
        dest.write_text(code)
        manifest.append({
            "file": dest.name,
            "kernel_ref": ref,
            "author": author,
            "votes": int(r["totalVotes"]),
            "kernel_last_run": r["lastRunTime"][:19],
            "sha256": hashlib.sha256(code.encode()).hexdigest(),
            "lines": code.count("\n") + 1,
            "author_lb_rating_at_pull": ratings.get(author.lower()),
        })
        print(f"  ok   {ref} -> {dest.name} ({manifest[-1]['lines']} lines, "
              f"author rating {manifest[-1]['author_lb_rating_at_pull']})")

    (POOL / "MANIFEST.json").write_text(json.dumps(
        {"pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "competition": COMP, "sort": args.sort, "agents": manifest}, indent=2) + "\n")
    print(f"\n{len(manifest)} agents -> {POOL/'MANIFEST.json'}")


if __name__ == "__main__":
    main()
