"""1エージェント = 1ブランチ。許可制ワークツリーで走らせる。

    python tools/run_agent.py r1-13-sol-low-p1
    python tools/run_agent.py <run-id> --cli codex --model gpt-5.6-sol \
                              --reasoning-effort low --arm p1

**除外方式ではなく許可制**でワークツリーを組む。NEDO ラウンド1 では除外パターン
`r1-*` が `_score/r1-08/` に一致せず素通りし、他個体の解が子から見えた。
渡すものを列挙する方式なら、増やし忘れは動かないだけで済み、漏らしても情報は出ない。

**渡さないもの: `opponents/`(採点材料)、`baseline/`(公開解由来)、`results/`、
`tools/eval_field.py` / `refresh_opponents.py` / `lb_snapshot.py`(採点系)。**

プロンプトは argv ではなく `PROMPT.md` に置く。NEDO ではプロンプトを argv に載せたせいで
エージェントの `pgrep -f` が自分自身にマッチし、2時間45分ぶんの実行を SIGKILL した。
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / ".runs"

REGISTRY = {
    "r1-01-opus-p1":     dict(cli="claude", model="claude-opus-5",     arm="p1"),
    "r1-02-opus-p1":     dict(cli="claude", model="claude-opus-5",     arm="p1"),
    "r1-03-opus-p3":     dict(cli="claude", model="claude-opus-5",     arm="p3"),
    "r1-04-opus-p3":     dict(cli="claude", model="claude-opus-5",     arm="p3"),
    "r1-05-fable-p1":    dict(cli="claude", model="claude-fable-5-1",  arm="p1"),
    "r1-06-fable-p1":    dict(cli="claude", model="claude-fable-5-1",  arm="p1"),
    "r1-07-fable-p3":    dict(cli="claude", model="claude-fable-5-1",  arm="p3"),
    "r1-08-fable-p3":    dict(cli="claude", model="claude-fable-5-1",  arm="p3"),
    "r1-09-sol-xhigh-p1": dict(cli="codex", model="gpt-5.6-sol", arm="p1", reasoning_effort="xhigh"),
    "r1-10-sol-xhigh-p1": dict(cli="codex", model="gpt-5.6-sol", arm="p1", reasoning_effort="xhigh"),
    "r1-11-sol-xhigh-p3": dict(cli="codex", model="gpt-5.6-sol", arm="p3", reasoning_effort="xhigh"),
    "r1-12-sol-xhigh-p3": dict(cli="codex", model="gpt-5.6-sol", arm="p3", reasoning_effort="xhigh"),
    "r1-13-sol-low-p1":   dict(cli="codex", model="gpt-5.6-sol", arm="p1", reasoning_effort="low"),
    "r1-14-sol-low-p1":   dict(cli="codex", model="gpt-5.6-sol", arm="p1", reasoning_effort="low"),
    "r1-15-sol-low-p3":   dict(cli="codex", model="gpt-5.6-sol", arm="p3", reasoning_effort="low"),
    "r1-16-sol-low-p3":   dict(cli="codex", model="gpt-5.6-sol", arm="p3", reasoning_effort="low"),
}

# 許可制。ここに書いたものだけがワークツリーに入る。
ALLOW_FILES = ["AGENTS.md", "requirements.txt",
               "docs/competition_brief.md",
               "docs/env/RULES.md", "docs/env/GETTING_STARTED.md", "docs/env/kaggriculture.json",
               "tools/engine.py", "tools/eval_local.py",
               "tools/validate_submission.py", "tools/build_submission.sh"]


def build_worktree(run_id: str, arm: str) -> Path:
    work = RUNS / run_id
    if work.exists():
        shutil.rmtree(work)
    for rel in ALLOW_FILES:
        src = REPO / rel
        if not src.is_file():
            raise SystemExit(f"allow-list names a file that does not exist: {rel}")
        dst = work / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    shutil.copy2(REPO / "prompts" / "v1" / f"{arm}.md", work / "PROMPT.md")
    # 実行環境。ワークツリーに venv を複製するのは重いので共有 venv へのシンボリックリンク。
    venv = Path(os.environ.get("KAGGRICULTURE_VENV", "/home/vscode/.venvs/kaggriculture"))
    if not (venv / "bin" / "python").exists():
        raise SystemExit(f"runtime venv missing: {venv} (see tools/README.md)")
    (work / ".venv").symlink_to(venv)
    leaked = [p for p in work.rglob("*") if not p.is_symlink() and ".venv" not in p.parts
              and p.is_file() and any(s in p.parts for s in ("opponents", "baseline", "results"))]
    if leaked:
        raise SystemExit(f"worktree leak: {leaked}")
    return work


def command(cfg: dict, work: Path) -> list[str]:
    one_line = "PROMPT.md を読んで、その指示に従って作業せよ。"
    if cfg["cli"] == "codex":
        return ["codex", "exec", "--skip-git-repo-check", "--json",
                "-m", cfg["model"],
                "-c", f'model_reasoning_effort="{cfg.get("reasoning_effort", "xhigh")}"',
                "-s", "danger-full-access", "-C", str(work), one_line]
    if cfg["cli"] == "claude":
        return ["claude", "-p", one_line, "--output-format", "stream-json", "--verbose",
                "--dangerously-skip-permissions", "--model", cfg["model"], "--max-turns", "1000"]
    raise SystemExit(f"unknown cli {cfg['cli']!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--cli"); ap.add_argument("--model")
    ap.add_argument("--arm", choices=("p1", "p3")); ap.add_argument("--reasoning-effort")
    args = ap.parse_args()

    cfg = dict(REGISTRY.get(args.run_id, {}))
    for k, v in (("cli", args.cli), ("model", args.model), ("arm", args.arm),
                 ("reasoning_effort", args.reasoning_effort)):
        if v:
            cfg[k] = v
    if not {"cli", "model", "arm"} <= cfg.keys():
        raise SystemExit(f"unknown run-id {args.run_id!r}: give --cli/--model/--arm")

    work = build_worktree(args.run_id, cfg["arm"])
    out = RUNS / f"{args.run_id}.jsonl"
    meta = {"run_id": args.run_id, "config": cfg,
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "workdir": str(work)}
    (RUNS / f"{args.run_id}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, ensure_ascii=False))

    t = time.time()
    with out.open("w") as fh:
        # setsid: 親のプロセスグループに紐づけない。ハーネスがバックグラウンドジョブへ
        # SIGSTOP を送ってプロセス群ごと落とした事故が NEDO であった。
        proc = subprocess.Popen(command(cfg, work), stdout=fh, stderr=subprocess.STDOUT,
                                cwd=str(work), start_new_session=True,
                                env={**os.environ, "KAGGLE_USERNAME": "", "KAGGLE_API_TOKEN": ""})
        rc = proc.wait()
    meta.update(returncode=rc, elapsed_sec=round(time.time() - t, 1),
                finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    (RUNS / f"{args.run_id}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"run_id": args.run_id, "returncode": rc,
                      "elapsed_sec": meta["elapsed_sec"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
