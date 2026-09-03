# Kaggle `kaggriculture` — ERL 開発リポジトリ

2人対戦の農業経営シミュレーションで動くエージェントを、population で開発するためのリポジトリ。
**締切 2026-09-30 23:59 UTC**、Featured / メダル付与あり、7,396チーム、賞金 $50,000。

**親プロジェクト:** [epistemic-research-loop](https://github.com/sota1111/epistemic-research-loop)
——エージェント population を回して未知構造の発見と実スコア最大化を狙うループの実装。
本リポジトリはそのループを**このコンペ専用に走らせるための開発リポジトリ**であり、
ラウンドごとの計画・エージェントの成果物・実提出の記録を GitHub 上に永続化する。

> **なぜ分けたか:** 2026-09-02 に dev container が作り直され、`.runs/` に置いていた
> エージェント成果物がすべて失われた。コミットされていた docs だけが残った。
> 以後、**成果物は必ずリポジトリに残す。**

## いま知っておくべき3つのこと

1. **LB スコアは所持金ではなくレーティング。** 新規提出は必ず **600.0 から始まり**、
   対戦を重ねて収束する。**提出直後の値で候補を評価してはならない。**
2. **LB はチームの最高スコアではなく、現在アクティブな提出を表示する。**
   2026-08-03 に 2543.4(現盤面で 165位=銀圏)を出した moon-198 を放置して
   弱い個体を出し続けたため、順位は 3,251 位まで落ちていた。**良い個体は置いておく。**
3. **ローカル評価は実 LB の順序を反転させることが実証済み。**
   昇格判定は実 LB のレーティングでのみ行う(`docs/competition_brief.md` §5.1)。

## ブランチ運用

| ブランチ | 役割 |
| --- | --- |
| `main` | **コンペ正本・評価基盤・ラウンド計画のみ。** エージェントはここを読んでよい |
| `agent/r<N>-<id>-<config>` | **1 エージェント = 1 ブランチ。** 成果物をここに残す |

## 中身

| パス | 内容 |
| --- | --- |
| [`docs/competition_brief.md`](docs/competition_brief.md) | **コンペ正本。**エージェントが最初に読む |
| [`docs/round1_plan.md`](docs/round1_plan.md) | ラウンド1計画(事前登録) |
| [`docs/decision_2026-09-03.md`](docs/decision_2026-09-03.md) | 参戦判断(kaggriculture 対 biohub)の実測記録 |
| `docs/env/` | 公式ルールのベンダリング(`kaggle-environments` 1.32.7、Apache-2.0) |
| [`AGENTS.md`](AGENTS.md) | エージェントへの契約 |
| `baseline/moon198/` | **実 LB 2543.4 実証済みの基準個体**(公開カーネル蒸留、出自は正本 §7) |
| `opponents/` | 公開上位5体の相手プール + `MANIFEST.json`(出自・sha256) |
| `tools/` | 評価基盤([`tools/README.md`](tools/README.md)) |
| `results/lb/` | LB スナップショット(メダルラインの推移) |
| `results/baseline/` | 基準個体のローカル測定 |
| `results/r<N>/` | 各ラウンドの成果物 |

## セットアップ

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # KAGGLE_USERNAME / KAGGLE_API_TOKEN を記入

# 基準個体が動くことの確認(約2秒)
python tools/eval.py baseline/moon198/main.py opponents/soil_remembers_rain.py 42

# いまのメダルラインを引き直す
python tools/lb_snapshot.py --score 2543.4 --team "$KAGGLE_USERNAME"
```

## 提出(Controller のみ)

```bash
bash tools/build_submission.sh results/r1/<agent-id>
kaggle competitions submit -c kaggriculture -f results/r1/<agent-id>/submission.tar.gz -m "..."
```

**5回/日。**エージェントは提出しない。締切24時間前は新規提出を停止し、
最も収束レーティングの高い個体をアクティブにしたまま締切を迎える。
