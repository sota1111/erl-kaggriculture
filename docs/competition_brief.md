# コンペ正本 — Kaggle `kaggriculture`

**最終更新: 2026-09-03**(このファイルが本リポジトリの一次情報。エージェントは最初にこれを読む)

| | |
| --- | --- |
| URL | https://www.kaggle.com/competitions/kaggriculture |
| 主催 | Kaggle |
| カテゴリ | Featured / **メダル付与あり**(`awards_points = True`) |
| 締切 | **2026-09-30 23:59 UTC** |
| チーム合流・新規参加締切 | 2026-09-23 23:59 UTC(**参加済み**) |
| 賞金 | $50,000(上位10チームに各 $5,000) |
| 提出物 | `main.py` を root に持つ `submission.tar.gz`(または `main.py` 単体) |
| 提出上限 | **5回/日** |
| チーム上限 | 5人 |
| 環境 | `kaggle-environments` の `kaggriculture` env(**本リポジトリは 1.32.7 にピン**) |

## 1. スコアの正体 — 金額ではなく **レーティング**

**ここを間違えると全ての判断が狂う。**

- ゲームの `reward` は**シーズン終了時の所持金**(ローカルでは 10 万台になる)。
- しかし**リーダーボードのスコアは所持金ではなく、対戦を通じて更新されるレーティング**。
  新規提出は **600.0 から始まり**、エピソードを重ねて真の実力へ収束していく。
  実測: 2026-09-03 に再提出した moon-198 は受理直後 `600.0`。
- したがって:
  1. **提出直後のスコアを候補の評価に使ってはならない。** 収束を待つ。
  2. **収束には時間がかかる。**締切間際の提出は登り切らない。**早く出すこと自体が価値を持つ。**
  3. 600 付近は「まだ登っていない」と「実力が低い」の区別がつかない
     (SOT-2379: soil は実 LB で 600 に張り付いた)。
- LB は**そのチームの最高スコアではなく、現在アクティブな提出**を表示する。
  2026-08-03 に 2543.4 を出した moon-198 を放置し、以後 gpt 系(897.2)を出し続けたため
  順位が 3,251 位まで落ちていた。**良い個体を「置いておく」ことが必要。**

## 2. メダルライン(2026-09-03 実測、`tools/lb_snapshot.py`)

7,396 チーム。1,000 チーム超なので銅=上位10%、銀=上位5%、金=上位10位+0.2%。

| | 順位 | スコア |
| --- | ---: | ---: |
| 金 | 24 | 2820.6 |
| 銀 | 369 | 2293.5 |
| **銅** | **739** | **1957.2** |
| 上位20% | 1,479 | 1524.9 |
| 中央値 | 3,698 | 759.6 |

**参考:** moon-198 の 2543.4(2026-08-03 の値)は、この盤面に当てはめると 165 位=上位 2.23%(銀圏)。
ただしレーティングは相対値であり、フィールドは日々強くなる。**再測定が必要**(§6)。

閾値は締切に向かって上がる。判断のたびに `python tools/lb_snapshot.py` で引き直すこと。

## 3. ゲーム仕様(要点)

完全なルールは **`docs/env/RULES.md`**(公式 README)と **`docs/env/GETTING_STARTED.md`**、
機械可読な設定は **`docs/env/kaggriculture.json`** にベンダリングしてある
(`kaggle-environments` 1.32.7 由来、Apache-2.0)。**迷ったら env のソースが正本。**

- **2人対戦**。各プレイヤーが 10×10 の農場(5×5 の4象限、初期は NW のみ解放)を経営する。
- **1シーズン = 30日 × 24ターン = 720ステップ**。`actTimeout = 1 秒/ターン`。
- **初期資金 $3,000**。勝利条件はシーズン終了時の所持金。
- **作物** Wheat / Carrot / Tomato(継続) / Strawberry(継続) / Melon。
  水やりボーナス窓、`FERTILIZE` による倍化、2日連続の水やり忘れで雑草化(回復不能)。
- **家畜** Goose(卵・要 COOP)/ Cow(牛乳)/ Sheep(羊毛、要 PASTURE)。
  毎日 wheat を給餌。2日連続の給餌忘れで逃亡(回復不能)。`CARE` は次回生産にボーナス加算。
- **土地** NE $1,000 / SW $2,000 / SE $4,000 を `BUY_LAND` で解放。
- **雇用** 1日あたりの n 人目の雇用コストは `fib(n)`(1,1,2,3,5,8,13,…)、毎日リセット。
  雇った hand も毎ターン独立に行動する。
- **市場** 販売価格は市場在庫に対して動的。`base` は共有初期在庫 `I0` での価格で、
  在庫が減れば上がり、増えれば下がる。形状関数(linear/sq/sqrt/log/hinge)は商品ごと・
  `I0` の上下で別。**高級品(strawberry / melon / milk / wool)は供給過剰で $1 の床まで崩れる。**
  買い戻せるのは wheat と fertilizer のみ。**市場注文は 1ターン 10件まで**(超過分は黙って捨てられる)。
- **町** 町の中心が毎日 1 個ずつ全商品を買う。3日ごとに店が解放され(**重複あり**、最大8）、
  各店は 4 ターンごとに担当商品を消費する。**需要は単調増加する。**
- **納屋** 非種アイテム 100 個まで。日終わりの投入で溢れた分は破棄。

## 4. 提出の契約

```python
def agent(obs):
    return {"farmer": [op, *args], "hands": [[op, *args], ...], "market": [[op, *args], ...]}
```

- `main.py` が archive の root にあり、`agent(obs)` を export していること。
  `tools/validate_submission.py` がこの契約を機械的に確認する。
- 不正なアクションは**黙って no-op** になる。例外を投げると評価が落ちる。
- **1ターン 1秒**の制限。720 ターン分の累積予算は `remainingOverageTime = 60` 秒。
- 外部ネットワークには出られない。モデル重みは archive に同梱すること。

## 5. ローカル評価基盤

| ツール | 用途 | 信頼度 |
| --- | --- | --- |
| `tools/validate_submission.py` | 提出契約の機械チェック | **信頼できる**(契約は明文) |
| `tools/build_submission.sh` | `submission.tar.gz` の生成 + sha256 記録 | **信頼できる** |
| `tools/eval.py` | 候補 vs 相手 1体 の総当たり(所持金差) | **参考値のみ** |
| `tools/eval_league.py` | 公開上位5体の相手プールに対する field win-rate | **昇格判定に使ってはならない**(§5.1) |
| `tools/lb_snapshot.py` | 実 LB の取得とメダルライン算出 | **信頼できる**(実測) |

1エピソードは **約 2 秒**(moon-198 vs starter、seed 42、実測)。
5相手 × 12 seed × 両席 = 120 戦でも数分。**ローカル試行は安い。**

### 5.1 ローカル評価は実 LB の順序を反転させる(実証済み)

`kaggriculture-claude` SOT-2417 の結論:

- self-mirror オラクル(候補 vs 現champion)では soil が moon-198 に **20/20 で勝った**。
  実 LB では **moon-198 = 2543.4、soil = 600(床)**。
- 公開上位5体で組んだ replay-league でも順序は**反転**した
  (moon-198 の field win-rate 27.5% < soil)。較正は **CALIBRATED = False** で終わっている。

**これは IEEE-CIS のローカル AUC 順位と実 public score の相関 ρ=-1.000、
NEDO の採点系欠陥(ローカル指標が実は別の量を測っていた)と同型の失敗である。**

したがって本コンペの運用規約:

> **昇格判定は実 LB のレーティングでのみ行う。ローカル評価は「明らかな破綻の足切り」
> (例外を投げる・所持金が starter 以下・タイムアウト)にのみ使う。**

実 LB の予算は **5回/日 × 締切まで**。これが唯一の真値であり、有限資源である。

## 6. 現在地(2026-09-03)

- **moon-198 を再提出済み**(submission `55971967`、`main.py` sha256 `7c5a4a2a…`)。
  受理時 600.0。**収束後の値がラウンド1の親スコアになる。**
- 旧 auto-improve 系統(`kaggriculture-claude` / `kaggriculture-gpt`)は**凍結**。
  以後の開発は本リポジトリで ERL のループとして行う。
- gpt / sol リネージは打ち切り。claude 系に対する劣位が
  本コンペ(claude 2543.4 対 gpt 897.2、同時期)でも NEDO でも実測で確定している。

## 7. baseline / 相手プールの出自

**すべて公開カーネル由来であり、独自成果ではない。**`opponents/MANIFEST.json` に
`kernel_ref` / sha256 / 抽出方式を記録してある。

| ファイル | 出自 |
| --- | --- |
| `baseline/moon198/main.py` | 公開カーネル `prvsiyan/…the-moon-counts-melons`(episode 89674601)の 198行蒸留。**実 LB 2543.4 実証済み** |
| `opponents/moon_counts_melons.py` | 同カーネルの 449行更新版 |
| `opponents/soil_remembers_rain.py` | `prvsiyan/…the-soil-remembers-rain` |
| `opponents/kaitofukami_v17_market_ranker.py` | `kaitofukami/…v17-learned-market-ranker`(学習型、別アーキテクチャ) |
| `opponents/pilkwang_economic_control.py` | `pilkwang/kaggriculture-observable-economic-control` |
| `opponents/roman_hamburger_anchor.py` | `romantamrazov/kaggriculture-hamburger` |

**ERL で積み上げる分は、この baseline からの上積みとして測る。**
