# `r1-13-sol-low-p1` — 評価基盤の初回通し(2026-09-03)

| | |
| --- | --- |
| config | `codex` / `gpt-5.6-sol` / `model_reasoning_effort="low"` / アーム P1 |
| 所要 | **256.8 秒**、rc=0 |
| 成果物 | `main.py`(7,056バイト)、`agent_submission.json`(必須キー全て)、`local_eval.json` |
| 契約チェック | PASS |
| 事後監査 | **ヒット3件、すべて偽陽性。**`tools/collect_run.py` の広い正規表現が、エージェントの `rg --files -g 'baseline/**' -g 'opponents/**'` に反応した——当時の `AGENTS.md` がそれらを参照していたため**存在を確認しに行った**もので、ディレクトリ自体が無く何も読めていない。`kaggle kernels` の実行なし。transcript 中の唯一の kaggle.com/code URL は、こちらが渡した `docs/competition_brief.md` の引用。**v0.4.6 で採点ツール自身のソースを読んだことによる偽陽性が3件出たのと同型** |

## 現在の公開プールに対する採点(216戦、両席、seed 1001-1012)

| 相手 | 勝敗 | マージン平均 |
| --- | ---: | ---: |
| `kaggriculture_structured_economic_policy` | 0/24 | -130,489 |
| `40_40_early_floor_v48_fast_routes` | 0/24 | -142,057 |
| `v16_rc5_high_score_8c_4s_premium_market_lead` | 0/24 | -139,849 |
| `kaggriculture_findings_from_zero_to_top_meta` | 0/24 | -131,911 |
| `v16_rc2_high_score_near_mirror_market_relay` | 0/24 | -140,333 |
| `kaggriculture_multi_route_farming_agent` | 0/24 | -146,668 |
| `25_27_strict_future_v27_midgame_meta_reset` | 0/24 | -140,234 |
| `177_180_fresh_top_30_v21_1_conditional_memory` | 0/24 | -121,993 |
| `kaggriculture_visualized_what_every_crop_pays` | **24/24** | +7,210 |
| **合計** | **24/216 = 11.1%** | **-120,703** |

`starter` に対する所持金 15,234(zero-bank 0/12)。最悪ターン 0.017 秒(制限1秒)。

## 基盤について分かったこと — 勝率はこの水準で使えない

**`baseline/moon198` も同じ 24/216 = 11.1% だった。**両者ともプール9体中8体に全敗し、
玩具のような1体(可視化ノート付属の83行エージェント)に全勝する。
**勝率が 24 の倍数に量子化され、実力が桁で違う個体を区別できない。**

| | 勝率 | マージン平均 |
| --- | ---: | ---: |
| `baseline/moon198` | 11.1% | **-1,100** |
| `r1-13-sol-low-p1` | 11.1% | **-120,703** |

**マージンは 100 倍離れており、こちらは分離する。**
以後、候補の順位付けは `margin_mean` で行う(`docs/round1_plan.md` §4.1b)。
`eval_field.py` はこの状態を検出して RESOLUTION WARNING を出すようにした。

> この取り違えは、「勝率が一致したのにマージンが100倍違う」という不自然さを追ったから
> 見つかった。**IEEE-CIS・NEDO と同型の「指標が別の量を測っている」失敗**であり、
> 今回は候補を並べ始める前に検出できた。

## 中身の評価 — 誘導なしで市場の結合に到達した

`rejected_hypotheses` より:

> 「全期間メロン単作: 基準価格では高収益だが、**共有市場で両者が売ると価格下落に
> 追随できず自己対戦収益が崩れた**」

**P1(誘導なし)アームの sol low が、自己対戦だけを手がかりに共有市場の結合を独立に発見した。**
`tools/eval_local.py` に自己対戦を入れた設計が効いている。
他に「距離優先の作業割当が回復不能な枯死を招く」「種の先買いが現金を固定する」
「最終日の手持ち在庫は現金化されない」を自力で発見・修正している。

## 判定

- **実行基盤は通った。**許可制ワークツリー、PROMPT.md 経由の起動、独立セッション、
  契約チェック、事後監査、採点、成果物回収まで一通り動作した。
- **候補としては弱い。**マージンで `baseline/moon198` の 100 倍負けている。
  ただし `sol low` は4分・1回の試行であり、この1件で effort 軸を語ってはならない
  (NEDO の教訓:実行間ばらつき自体がモデル依存)。replicate と他アームが要る。
