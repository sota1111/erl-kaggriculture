| run | model | effort | arm | 所要 | starter戦 bank | 基準線比 | マージン | 監査 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `r1-11-sol-xhigh-p3` | gpt-5.6-sol | xhigh | P3 | 3293s | 70,246 | 47% | -75,410 | 0 |
| `r1-09-sol-xhigh-p1` | gpt-5.6-sol | xhigh | P1 | 2776s | 70,975 | 47% | -83,138 | 0 |
| `r1-15-sol-low-p3` | gpt-5.6-sol | low | P3 | 414s | 22,840 | 15% | -115,401 | 0 |
| `r1-13-sol-low-p1` | gpt-5.6-sol | low | P1 | 257s | 14,784 | 10% | -117,193 | 1 |
| `r1-14-sol-low-p1` | gpt-5.6-sol | low | P1 | 405s | 18,018 | 12% | -121,462 | 0 |

> **注意: 2つのローカル指標が順位で食い違っている。**
> bank 順 r1-09-sol-xhigh-p1 > r1-11-sol-xhigh-p3 > r1-15-sol-low-p3 > r1-14-sol-low-p1 > r1-13-sol-low-p1
> マージン順 r1-11-sol-xhigh-p3 > r1-09-sol-xhigh-p1 > r1-15-sol-low-p3 > r1-13-sol-low-p1 > r1-14-sol-low-p1
> どちらが実LBの順位を保存するかは未検証であり、現時点でローカル順位を昇格判定に使ってはならない。

> **アーム内のばらつき(bank)最大 3,234 対 アーム間の差 54,575。**

**未採点(エピソード未実行):**
- `r1-01-opus-p1` — claude-opus-5 / - / P1 / 3308s
- `r1-03-opus-p3` — claude-opus-5 / - / P3 / 3104s
