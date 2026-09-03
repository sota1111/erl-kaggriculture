"""エージェント自身が使うローカル採点。組み込み相手と自己対戦のみ。

識別力は低い。組み込み `starter` は弱く、実力の異なるエージェントが所持金では
10% 以内に密集することが実測されている。ここで測れるのは「壊れていないこと」と
「相手が強いときに戦略が崩れないか(自己対戦)」まで。
本当の順位付けは Controller が非公開の相手フィールドに対して行う。

    python tools/eval_local.py main.py [--seeds 12]
"""
from __future__ import annotations
import argparse, statistics, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _one(task):
    import engine
    cand, opp, seed, seat = task
    a = engine.load_agent(cand)
    b = engine.builtin(opp) if opp in ("starter", "random", "pass") else engine.load_agent(opp)
    t = time.time()
    x, y = engine.play(a, b, seed) if seat == 0 else engine.play(b, a, seed)
    mine, theirs = (x, y) if seat == 0 else (y, x)
    return opp, seed, seat, mine, theirs, time.time() - t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    cand = str(Path(args.candidate).resolve())
    seeds = list(range(1, args.seeds + 1))
    tasks = [(cand, opp, s, seat)
             for opp in ("starter", "random", cand)
             for s in seeds for seat in (0, 1)]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(_one, tasks, chunksize=2))

    ok = True
    for opp in ("starter", "random", cand):
        sel = [r for r in rows if r[0] == opp]
        mine = [r[3] for r in sel]
        wins = sum(1 for r in sel if r[3] > r[4])
        label = "自己対戦" if opp == cand else opp
        zero = sum(1 for m in mine if m <= 0)
        print(f"  vs {label:10s}  bank平均 {statistics.mean(mine):>10,.0f}  "
              f"最小 {min(mine):>10,.0f}  勝ち {wins}/{len(sel)}"
              + (f"   ZERO-BANK {zero}" if zero else ""))
        if opp != cand and (zero or wins < len(sel)):
            ok = False
    worst = max(r[5] for r in rows)
    print(f"\n  1エピソードの最悪実行時間 {worst:.2f}s (720ターン)  "
          f"→ 1ターンあたり約 {worst/720*1000:.1f}ms")
    print("  破綻チェック:", "PASS" if ok else "FAIL(組み込み相手に負ける、または bank 0 の seed がある)")


if __name__ == "__main__":
    main()
