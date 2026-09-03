# 相手プールの較正試行(2026-09-03)— 代理指標では較正できなかった

`tools/eval_field.py --round-robin`(9体、両席、12 seed、各192戦)の結果を、
`MANIFEST.json` が記録した**作者の現在のLBレーティング**と突き合わせた。

| プールのエージェント | ローカル総当たり勝率 | 作者の現LB |
| --- | ---: | ---: |
| `kaggriculture_structured_economic_policy` | 100.0% | 2268.1 |
| `40_40_early_floor_39_46_top_10_v48_fast_routes` | 80.7% | 2279.1 |
| `v16_rc5_high_score_8c_4s_premium_market_lead` | 74.0% | 2515.4 |
| `kaggriculture_findings_from_zero_to_top_meta` | 51.6% | 1927.5 |
| `v16_rc2_high_score_near_mirror_market_relay` | 50.0% | 2515.4 |
| `kaggriculture_multi_route_farming_agent` | 43.8% | 2178.1 |
| `25_27_strict_future_v27_midgame_meta_reset` | 37.5% | 2279.1 |
| `177_180_fresh_top_30_v21_1_conditional_memory` | 12.5% | 2279.1 |
| `kaggriculture_visualized_what_every_crop_pays` | 0.0% | 2763.8 |

**Spearman ρ = -0.217(n=9)。**

## この数字を「ローカル評価は使えない」と読んではならない

**代理指標の側が壊れている。**作者の現LBは*その作者が今出している提出*の評価であって、
ここで凍結したカーネルの評価ではない:

- `kaggriculture_visualized_what_every_crop_pays` は可視化ノートの付属エージェント(83行)で、
  ローカル 0%。作者 georgymamarin の 2763.8 は**明らかに別の提出の値**である。
- kaitofukami の3本は互いに別バージョンなのに、作者レーティングは全て同じ 2279.1 に潰れる。
- boatlee の2本も同様に 2515.4 で同値。

**つまり9点のうち実質的に独立な点は数点しかなく、しかもラベルが対応していない。
この較正は成立しない。**

## 一方で分かったこと

- **プールの総当たりは強い識別力を持つ**(0% 〜 100% に広がり、192戦で安定)。
- `baseline/moon198` はこのプールに対して **11.1%**(216戦)で、
  実LBの 900 前後(下位半分)という位置と符合する。

## 較正は ラウンド1 で行う

**自前の16個体なら、ローカル勝率と実LBレーティングの両方を同一個体について直接測れる。**
代理指標は要らない。`docs/round1_plan.md` §4.2。
