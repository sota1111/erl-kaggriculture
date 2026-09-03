# 評価基盤

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r ../requirements.txt      # kaggle-environments 1.32.7 + kagsim(C++エンジン)
```

| ツール | 用途 |
| --- | --- |
| `engine.py` | エピソード実行のバックエンド。**毎プロセスで kagsim を自己検査**し、失敗したら `kaggle_environments` に落ちる |
| `validate_submission.py` | 提出契約(`agent(obs)` と戻り値の3キー)の機械チェック |
| `build_submission.sh` | `submission.tar.gz` を作り sha256 を記録 |
| `refresh_opponents.py` | **現在の**公開カーネルから相手プールを作り直す(陳腐化するので毎ラウンド実行) |
| `eval_field.py` | 候補をプール全体と両席・多seedで対戦させ勝率とマージンを出す |
| `lb_snapshot.py` | 実 LB を取得しメダルラインと自分の位置を算出 |
| `rating_probe.py` | 提出の (スコア, エピソード) を採取。**時間ではなくエピソードで収束を判定する** |

## 使い方

```bash
# ラウンド開始時に必ず: 相手プールを引き直す(前回のプールは古い)
python tools/refresh_opponents.py --top 16

# 候補の採点(216戦 ≈ 70秒、kagsim + 24並列)
python tools/eval_field.py results/r1/<id>/main.py --seeds 12 --json results/r1/<id>/field.json

# プール自身の総当たり(ローカル順位が作者の現LBと合うかの較正材料)
python tools/eval_field.py --round-robin --seeds 12 --json results/baseline/pool_round_robin.json

# 提出の測定(定期的に叩いて系列を伸ばす)
python tools/rating_probe.py --append results/baseline/rating_convergence.md

# メダルラインを引き直す
python tools/lb_snapshot.py --score <その時点のスコア>
```

## 測れること・測れないこと(2026-09-03 実測)

| 指標 | 識別力 |
| --- | --- |
| 組み込み `starter` に対する所持金 | **ほぼ無い。**実力の異なる6体が 10% 以内、うち4体は 0.2% 以内に密集する |
| **現在の公開プールに対する両席・多seed勝率** | **有効。**`baseline/moon198` は 11.1% で、実LB 900前後(下位半分)と整合 |
| 実 LB レーティング | 唯一の真値。ただし動き続けるので「収束値」は存在しない |

**ローカル順位が実LB順位を保存するかは未確認。**ラウンド1 で n=16 の Spearman を取って
初めて答えが出る(`docs/round1_plan.md` §4.2)。それまでローカル順位は仮の順位である。

## エンジンの検証(2026-09-03、本リポジトリで実施)

- 同梱トレース5本すべてで C++ コアが 719 ステップ完全一致
- Python バインディングのゴールデンテスト PASS
- 自前エージェントでの照合: `moon198 vs starter` seed 42 →
  kagsim (133032.0, 3532.0) = kaggle_environments (133032.0, 3532.0)
- 速度 **19倍**(0.36秒 対 7.0秒)
- **アリーナのリプレイ JSON から設定を抽出して照合済み**——env `0.1.0`、全項目がローカル既定値と一致

**速いシミュレータが黙って本物とずれるのは、遅いより悪い。**`engine.py` は毎回自己検査する。

## 安全上の注意

**他人のノートブックからエージェントを取り出す処理は、必ずサンドボックス
(別プロセス + 一時ディレクトリ)で実行する。**`refresh_opponents.py` は
`_sandbox_extract.py` 経由でそうしている。この規約は、抽出処理がリポジトリ直下へ
他人の `main.py`(70KB)を書き出す事故を起こしてから追加された。
