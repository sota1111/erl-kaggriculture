"""ラウンドの全個体を1つの表にまとめる。

    python tools/round_summary.py [--round r1] [--md docs/round1_results.md]

**プールの取得日時が個体ごとに違ったら、その表は比較になっていない。**
`summary.json` が記録している `pool_pulled_at` を照合し、混在していたら警告する。
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REFERENCE_BANK = 150_000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", default="r1")
    ap.add_argument("--md", default="")
    args = ap.parse_args()

    rows = []
    for s in sorted((REPO / "results" / args.round).glob("*/summary.json")):
        d = json.loads(s.read_text())
        c = d.get("config") or {}
        rows.append(dict(run=d["run_id"], model=c.get("model", "?"),
                         effort=c.get("reasoning_effort", "-"), arm=c.get("arm", "?"),
                         sec=d.get("elapsed_sec"), bank=d.get("bank_vs_starter_mean"),
                         margin=d.get("margin_mean"), win=d.get("win_rate"),
                         audit=d.get("audit_hits"), pool=d.get("pool_pulled_at")))
    if not rows:
        raise SystemExit(f"results/{args.round}/*/summary.json がない")

    rows.sort(key=lambda r: -(r["margin"] or -9e18))
    pools = {r["pool"] for r in rows}
    lines = [f"| run | model | effort | arm | 所要 | starter戦 bank | 基準線比 | マージン | 監査 |",
             "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for r in rows:
        pct = f"{(r['bank'] or 0) / REFERENCE_BANK * 100:.0f}%"
        lines.append(f"| `{r['run']}` | {r['model']} | {r['effort']} | {r['arm'].upper()} | "
                     f"{r['sec']:.0f}s | {r['bank']:,.0f} | {pct} | {r['margin']:,.0f} | {r['audit']} |")
    out = "\n".join(lines)
    print(out)
    print(f"\n基準線 = starter 戦 bank {REFERENCE_BANK:,}(現在の公開フィールドで戦えている水準)")
    if len(pools) > 1:
        print(f"\n**警告: プールの取得日時が混在している {sorted(pools)} — この表は比較になっていない。**")
    else:
        print(f"プール取得: {pools.pop()}")
    if args.md:
        Path(args.md).write_text(out + "\n")
        print(f"wrote {args.md}")


if __name__ == "__main__":
    main()
