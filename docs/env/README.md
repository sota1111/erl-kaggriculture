# ベンダリングされた公式ルール

`kaggle-environments` **1.32.7** の `kaggle_environments/envs/kaggriculture/` から
そのままコピーしたもの。ローカル環境が作り直されても、エージェントがオフラインで
正本を読めるようにするため(2026-09-02 に成果物を全消失させた反省)。

| ファイル | 元 | 内容 |
| --- | --- | --- |
| `RULES.md` | `README.md` | 公式ルール全文。作物表・価格関数・町の需要・ターン処理順 |
| `GETTING_STARTED.md` | `AGENTS.md` | observation / action の全仕様、提出手順 |
| `kaggriculture.json` | 同名 | 機械可読な env 仕様と `configuration` の既定値 |

Copyright Kaggle, Apache License 2.0。

**バージョンを上げるときは `requirements.txt` のピンと同時に更新し、
差分をコミットに残すこと**(ルール変更は評価の意味を変える)。
