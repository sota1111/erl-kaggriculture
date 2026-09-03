# code/ — verification and measurement for `../main.py`

`main.py` is standalone (`import math`, nothing else) and stateless. Everything
here is a tool, not part of the submission.

## Runs now (no episodes needed)

These were used to build and check the agent while episode execution was
switched off in this worktree.

| script | what it does |
| --- | --- |
| `fuzz_obs.py` | Builds random-but-plausible observations across the whole state space the engine can produce — both seats, every day/hour, every quadrant combination, weeds, decaying plants, escaped animals, empty/full sheds, and deliberately mangled observations — and asserts a legal action comes back, fast, without raising. 40,000 pass. |
| `test_invariants.py` | Eight hand-built scenarios covering the losses the rules call unrecoverable (starved herd, weeded field) and the ones that silently zero the score (unsold produce on day 29, PLANT orders dropped for exceeding seeds, market queue over the 10-order cap). |
| `timing_worst.py` | Adversarial timing: 100 unlocked tiles all occupied and all demanding attention at once, 12 hands, over every hour of every day, both seats. 4,320 turns. |
| `inspect_decisions.py` | Reading aid. Prints the town-demand model, the crop value table at various days/banks/holdings, and the action the agent picks on opening, mid-game and final-day boards. Use it to see *why* a decision was made. |

```bash
.venv/bin/python code/fuzz_obs.py --n 20000
.venv/bin/python code/test_invariants.py
.venv/bin/python code/timing_worst.py
.venv/bin/python code/inspect_decisions.py
```

## Needs episodes enabled

Both use `tools/engine.py`, which raises `SimulationDisabled` while
`.no_simulation` exists.

| script | what it does |
| --- | --- |
| `trace_episode.py` | One episode, dumping per-day bank, tile census, hand count, prices, shop unlocks, and the split of unit-actions actually issued. The action split is the diagnostic: if `MOVE` dominates the layout or `DIST_WEIGHT` is wrong; if `PASS` appears we are paying for hands we cannot use. |
| `sweep.py` | Parameter sweep over the constants `agent_submission.json → open_questions` could not settle. Every constant it touches is read at call time, so a worker loads `main.py` and overrides it in place — `main.py` is never edited. Scores each setting against `starter` **and** in self-play. |

```bash
.venv/bin/python code/trace_episode.py --seed 1 --seat 0 --opp starter
.venv/bin/python code/sweep.py --grid rival   --seeds 12 --workers 12
.venv/bin/python code/sweep.py --grid labour  --seeds 12
.venv/bin/python code/sweep.py --grid opening --seeds 12
.venv/bin/python code/sweep.py --grid selling --seeds 12
```

**Read the self-play column, not the starter column.** `starter` runs a single
carrot tile and never competes for a niche, so it cannot show whether a setting
survives a rival sharing the same market — which is the one thing every open
question turns on.
