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

## いま知っておくべき4つのこと

1. **過去の記録は根拠に使わない。** このコンペのフィールドは3週間で入れ替わる。
   8月のレーティングも、8月に抽出した相手プールに対する勝率も、現在の判断には使えない。
   相手プールは `tools/refresh_opponents.py` で**毎ラウンド引き直す。**
2. **LB スコアは所持金ではなくレーティングで、エピソード単位で動く。** 新規提出は 600.0
   から始まる。ラダーの供給速度はエージェントによって10倍違うので、**時間ではなく
   消化エピソード数で判定する**(`tools/rating_probe.py`)。**「収束値」は存在しない。**
3. **LB はチームの最高スコアではなく、現在対戦中の提出を表示する。**
   5回/日 出せても対戦に回るのは直近のものだけで、弱い個体で上書きすると良い個体が降りる。
4. **ローカルは `kagsim` で 19倍速く回る**(bit-exact 検証済み)。1候補 216戦が約70秒。
   **ローカル試行は事実上無制限、有限なのは実 LB だけ。**

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
| `baseline/moon198/` | 基準個体(公開カーネル蒸留、**ERL の成果ではない**)。現在 実LB 920.6 / プール勝率 11.1% |
| `opponents/` | **現在の**公開カーネルから作った相手プール + `MANIFEST.json`(取得日時・出自・sha256・作者の現LB) |
| `tools/` | 評価基盤([`tools/README.md`](tools/README.md)) |
| `results/lb/` | LB スナップショット(メダルラインの推移) |
| `results/baseline/` | 基準個体のローカル測定 |
| `results/r<N>/` | 各ラウンドの成果物 |

## セットアップ

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # KAGGLE_USERNAME / KAGGLE_API_TOKEN を記入

# 相手プールを現在の公開カーネルから作り直す
python tools/refresh_opponents.py --top 16

# 基準個体を現在のプールで採点(216戦 ≈ 70秒)
python tools/eval_field.py baseline/moon198/main.py --seeds 12

# いまのメダルラインを引き直す
python tools/lb_snapshot.py --team "$KAGGLE_USERNAME"
```

## 提出(Controller のみ)

```bash
bash tools/build_submission.sh results/r1/<agent-id>
kaggle competitions submit -c kaggriculture -f results/r1/<agent-id>/submission.tar.gz -m "..."
```

**5回/日。**エージェントは提出しない。締切24時間前は新規提出を停止し、
最も収束レーティングの高い個体をアクティブにしたまま締切を迎える。
