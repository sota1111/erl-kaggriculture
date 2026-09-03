# baseline `moon-198`

| | |
| --- | --- |
| `main.py` sha256 | `7c5a4a2a3ba51cc4dc00657614f28a0afa8ee275ce6cdd8e7cb6c2ac2b54840d` |
| 行数 | 198 |
| 出自 | 公開カーネル `prvsiyan/kaggriculture-frontier-the-moon-counts-melons`(episode 89674601)の蒸留。**独自成果ではない** |
| 由来リポジトリ | [`sota1111/kaggriculture-claude`](https://github.com/sota1111/kaggriculture-claude)(SOT-2368、champion of record) |
| **実 LB** | **2543.4**(2026-08-03)。2026-09-03 の盤面に当てはめると 165位 = 上位 2.23%(銀圏) |
| 再提出 | submission `55971967`(2026-09-03 01:43 UTC)、受理時 600.0 → 収束待ち |

## ローカル測定

| 対戦相手 | seed | 結果 |
| --- | --- | --- |
| 内蔵 `starter` | 42 | moon-198 **133,032** 対 starter 3,532 |

公開上位5体プールに対する field win-rate は **39/120 = 32.5%**(12 seed × 両席、
`results/baseline/moon198_league.json`、全 120 戦 `DONE`、ALL-WIN / ALL-LOSE の相手はゼロ)。

> **ローカルでは平均以下に見えるこの個体が、実 LB では 2543.4(銀圏)だった。**
> この一行が、本リポジトリでローカル評価を昇格判定に使わない理由そのものである。
> 再提出後の収束は `results/baseline/rating_convergence.md`。

## 既知の性質(`kaggriculture-claude` の測定より)

- **席不変**(SOT-2382: seat-diverse dual-route は棄却され、champion は seat-invariant)。
- 固定ポリシー。学習も探索木も持たない。
- self-mirror オラクルでは soil `00e8ab59` に 20/20 で負けるが、
  実 LB では soil が 600 に張り付き moon-198 が 2543.4 だった(SOT-2379)。
