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


def build_worktree(run_id: str, arm: str, resume: bool = False, no_sim: bool = False) -> Path:
    work = RUNS / run_id
    if work.exists() and not resume:
        shutil.rmtree(work)
    for rel in ALLOW_FILES:
        src = REPO / rel
        if not src.is_file():
            raise SystemExit(f"allow-list names a file that does not exist: {rel}")
        dst = work / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    shutil.copy2(REPO / "prompts" / "v1" / f"{arm}.md", work / "PROMPT.md")
    if no_sim:
        (work / ".no_simulation").write_text(
            "Controller がエピソード実行を停止している。engine.play は例外を投げる。\n")
        with (work / "PROMPT.md").open("a") as fh:
            fh.write("""
## 重要:このワークツリーではエピソードを実行できない

マシンが他の作業で飽和しているため、**Controller がシミュレーションを停止している。**
`tools/eval_local.py` と `tools/engine.py` の `play()` は例外を投げる。回避を試みないこと
(自前でエピソードを回す実装を書くのも同じく禁止)。

**この状態で進めること:**

- `main.py` を実装する。`agent(obs)` を export し、契約を満たすこと
- `.venv/bin/python tools/validate_submission.py main.py` は**動く**(1ターンぶんの
  スタブ観測で契約を検査するだけで、エピソードは回さない)。これは必ず通すこと
- `docs/env/RULES.md` と env のソースから、**測定なしで決められる設計判断**を進める
- **測定が必要な判断は、`agent_submission.json` の `rejected_hypotheses` ではなく
  `open_questions` に、何をどう測れば決まるかと併せて書く。**
  測っていないことを測ったように書いてはならない
- `code/` に測定スクリプトを置いておくのは有用。Controller が後で回す

採点は Controller が実施する。**あなたの終了条件は「契約を満たす `main.py` と、
測定待ちの問いを明記した `agent_submission.json`」である。**
""")
    # 実行環境。ワークツリーに venv を複製するのは重いので共有 venv へのシンボリックリンク。
    venv = Path(os.environ.get("KAGGRICULTURE_VENV", "/home/vscode/.venvs/kaggriculture"))
    if not (venv / "bin" / "python").exists():
        raise SystemExit(f"runtime venv missing: {venv} (see tools/README.md)")
    link = work / ".venv"
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(venv)
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
        # 既定の claude CLI はこのマシンの MCP 設定を継承する。素で起動した r1-01 / r1-03 は
        # WebSearch・WebFetch に加え **ユーザーの Gmail と Google Calendar のツール** を
        # 与えられていた(送信・削除を含む)。--dangerously-skip-permissions と組み合わせると
        # 承認なしで実行できる。実害は出なかった(両者とも Bash しか使わなかった)が、
        # 隔離の前提が崩れていた:WebFetch/WebSearch があれば公開解を直接取得できる。
        # --restricted で設定ファイルと MCP を無視し、--tools で許可制にする。
        return ["claude", "-p", one_line, "--output-format", "stream-json", "--verbose",
                "--strict-mcp-config",
                "--tools", "Bash", "Read", "Write", "Edit", "Glob", "Grep",
                "--dangerously-skip-permissions", "--model", cfg["model"], "--max-turns", "1000"]
    raise SystemExit(f"unknown cli {cfg['cli']!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--cli"); ap.add_argument("--model")
    ap.add_argument("--arm", choices=("p1", "p3")); ap.add_argument("--reasoning-effort")
    ap.add_argument("--resume", action="store_true", help="既存ワークツリーの成果物を残す")
    ap.add_argument("--no-simulation", action="store_true",
                    help="エピソード実行を機構的に禁止する(マシンが混んでいるとき)")
    args = ap.parse_args()

    cfg = dict(REGISTRY.get(args.run_id, {}))
    for k, v in (("cli", args.cli), ("model", args.model), ("arm", args.arm),
                 ("reasoning_effort", args.reasoning_effort)):
        if v:
            cfg[k] = v
    if not {"cli", "model", "arm"} <= cfg.keys():
        raise SystemExit(f"unknown run-id {args.run_id!r}: give --cli/--model/--arm")

    work = build_worktree(args.run_id, cfg["arm"], resume=args.resume, no_sim=args.no_simulation)
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
                                stdin=subprocess.DEVNULL,  # CLI が stdin を3秒待つのを避ける
                                cwd=str(work), start_new_session=True,
                                env={**os.environ, "KAGGLE_USERNAME": "", "KAGGLE_API_TOKEN": "",
                                     **({"KAGGRICULTURE_NO_SIM": "1"} if args.no_simulation else {})})
        rc = proc.wait()
    meta.update(returncode=rc, elapsed_sec=round(time.time() - t, 1),
                finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    (RUNS / f"{args.run_id}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"run_id": args.run_id, "returncode": rc,
                      "elapsed_sec": meta["elapsed_sec"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
