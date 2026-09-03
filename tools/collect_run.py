"""実行の成果物を回収し、採点し、監査して results/r<N>/<run-id>/ に残す。

    python tools/collect_run.py r1-15-sol-low-p3 [--seeds 12]

手作業でやると必ず取りこぼす。回収・契約チェック・事後監査・採点を1本にまとめてある。
**事後監査のヒットは棄却理由ではなく、人間が1件ずつ確認する対象である**
——v0.4.6 では採点ツール自身のソースを読んだことによる false positive が3件出た。
"""
from __future__ import annotations
import argparse, json, re, shutil, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = str(REPO / ".venv" / "bin" / "python") if (REPO / ".venv/bin/python").exists() else sys.executable

# 公開解を取りに行った痕跡。プールのファイル名・カーネル作者・取得コマンド。
AUDIT = re.compile(r"kaggle kernels|kaggle competitions (kernels|replay|episodes)|"
                   r"opponents/|prvsiyan|kaitofukami|pilkwang|boatlee|flexonafft|"
                   r"raykkretzschmar|georgymamarin|salemali", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id"); ap.add_argument("--round", default="r1")
    ap.add_argument("--seeds", type=int, default=12)
    args = ap.parse_args()

    work = REPO / ".runs" / args.run_id
    dest = REPO / "results" / args.round / args.run_id
    if not (work / "main.py").exists():
        raise SystemExit(f"{work}/main.py がない。実行は成果物を残さなかった")
    dest.mkdir(parents=True, exist_ok=True)

    for name in ("main.py", "agent_submission.json", "local_eval.json"):
        if (work / name).exists():
            shutil.copy2(work / name, dest / name)
    for extra in work.glob("*.py"):
        if extra.name != "main.py":
            shutil.copy2(extra, dest / extra.name)
    for src, dst in ((f"{args.run_id}.jsonl", "transcript.jsonl"),
                     (f"{args.run_id}.meta.json", "meta.json")):
        p = REPO / ".runs" / src
        if p.exists():
            shutil.copy2(p, dest / dst)

    print("== 契約チェック ==")
    subprocess.run([PY, str(REPO / "tools/validate_submission.py"), str(dest / "main.py")], check=False)

    print("== 事後監査 ==")
    hits = [l[:160] for l in (dest / "transcript.jsonl").read_text(errors="replace").splitlines()
            if AUDIT.search(l)] if (dest / "transcript.jsonl").exists() else []
    print(f"  {len(hits)} 件ヒット" + ("(人間が確認すること)" if hits else " — クリーン"))
    for h in hits[:5]:
        print("   ", h)

    print("== 現在の公開プールに対する採点 ==")
    subprocess.run([PY, str(REPO / "tools/eval_field.py"), str(dest / "main.py"),
                    "--seeds", str(args.seeds), "--json", str(dest / "field.json")], check=False)

    meta = json.loads((dest / "meta.json").read_text()) if (dest / "meta.json").exists() else {}
    field = json.loads((dest / "field.json").read_text())
    sub = next(iter(field["subjects"].values()))
    summary = {"run_id": args.run_id, "config": meta.get("config"),
               "elapsed_sec": meta.get("elapsed_sec"), "returncode": meta.get("returncode"),
               "win_rate": sub["win_rate"], "margin_mean": sub["margin_mean"],
               "bank_vs_starter_mean": sub.get("bank_vs_starter_mean"),
               "audit_hits": len(hits), "pool_pulled_at":
                   json.loads((REPO / "opponents/MANIFEST.json").read_text())["pulled_at"]}
    (dest / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print("\n" + json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
