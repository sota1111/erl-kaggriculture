# 評価基盤

```bash
pip install -r ../requirements.txt   # kaggle-environments==1.32.7 にピン
```

| ツール | 用途 | 信頼度 |
| --- | --- | --- |
| `validate_submission.py <main.py>` | 提出契約(`agent(obs)` と戻り値の3キー)の機械チェック | **信頼できる** |
| `build_submission.sh <agent-dir>` | `submission.tar.gz` を作り sha256 を記録 | **信頼できる** |
| `lb_snapshot.py` | 実 LB を取得しメダルラインと自分の位置を算出 | **信頼できる**(実測) |
| `eval.py <cand> <opp> [seeds]` | 候補 対 相手1体 の総当たり(所持金差) | **足切りのみ** |
| `eval_league.py [cand]` | 公開上位5体のプールに対する field win-rate、両席・held-out seed | **昇格判定に使ってはならない** |
| `extract_opponents.py` | 公開カーネルから相手エージェントを抽出し `MANIFEST.json` を更新 | — |

## eval_league.py を昇格判定に使ってはならない理由

`kaggriculture-claude` SOT-2383 / SOT-2417 の記録:

- self-mirror オラクルでは soil が moon-198 に **20/20 で勝った**。
  実 LB では **moon-198 = 2543.4、soil = 600(床)**。
- 公開上位5体で組んだ replay-league でも順序は**反転**した
  (moon-198 の field win-rate 27.5%)。較正は **`CALIBRATED = False`** で終わっている。

**ローカルで測れるのは「壊れていないこと」までである。**強さの順序は実 LB でしか測れない。

## 使い方

```bash
# 契約チェック → archive 生成(sha256 を記録)
python tools/validate_submission.py results/r1/<id>/main.py
bash   tools/build_submission.sh   results/r1/<id>

# 破綻チェック(1エピソード約2秒)
python tools/eval.py results/r1/<id>/main.py opponents/soil_remembers_rain.py 7,42,101,202
python tools/eval_league.py results/r1/<id>/main.py --seeds all --json results/r1/<id>/local_eval.json

# 決定性の確認(タイムアウト・乱数由来の再現不能を検出)
python tools/eval_league.py results/r1/<id>/main.py --check-determinism

# メダルラインを引き直す
python tools/lb_snapshot.py --score <converged-rating>
```

seed 分割は SOT-2383 との継続性のため固定: SCREEN `[101, 202]` /
CONFIRM `[7, 42, 303, 404, 505, 777, 1234, 2026, 5555, 9001]`。**両席で走る。**
