# Coordination runs

The LLM meta-supervisor ([train_supervisor_coordination.py](../../train_supervisor_coordination.py))
on the four-tank setpoint-coordination test bed. Each run has two folders with the same name:

- `generated_supervisors_coordination/<run>/`: every candidate (`supervisor_gen_N_cK.py`), every
  promoted one (`best_supervisor_gen_N.py`) and the run's champion (`current_supervisor.py`).
- `results/coordination/<run>/`: `trials.jsonl` (one line per candidate: decision, score, the
  model's analysis and change, token usage), `evaluations.jsonl` (per-scenario metrics of every
  evaluated program), `context_report.jsonl` (lessons learned), `run_log.txt`, `summary.csv`,
  `final_report.md`, and from the run-folder layout on `invocations.jsonl` (settings and git commit of each start).

`baselines.csv` holds the fixed recipe, MPC and oracle MPC on the same scenarios
(`python benchmark_coordination.py`). All runs used deepseek-flash, at reasoning effort low unless the table says otherwise.

## Runs

Champion scores are re-scored on the current batteries (600 s window, 3 scenarios per cell:
42 dev / 42 held-out / 36 beyond), so every row is comparable. Lower is better.

| Run | Date | Setup (change from the run above) | Gens x candidates | Promoted | Est. cost | Champion dev / held-out / beyond |
|---|---|---|---|---|---|---|
| `window50_default` | 2026-10-01 | First run: 50 s window, 1 scenario per cell, per-scenario guard | 2 x 4 | 2 | $0.31 | 252.1 / 241.3 / 1260.8 |
| `window50_strictguard_run1` | 2026-10-01 | Three independent runs from the seed, same setup | 2 x 4 | 0 | $0.27 | 533.4 / 478.7 / 1583.0 (seed) |
| `window50_strictguard_run2` | 2026-10-01 | | 2 x 4 | 0 | $0.30 | 533.4 / 478.7 / 1583.0 (seed) |
| `window50_strictguard_run3` | 2026-10-01 | | 2 x 4 | 0 | $0.26 | 533.4 / 478.7 / 1583.0 (seed) |
| `window50_run1` | 2026-10-01 | Looser guard (per scenario, relative to the battery average) | 4 x 4 | 1 | $0.53 | 255.6 / 243.2 / 1189.8 |
| `window50_run2` | 2026-10-01 | | 4 x 4 | 2 | $0.35 | 226.3 / 242.2 / 1276.9 |
| `window50_run3` | 2026-10-01 | | 4 x 4 | 1 | $0.40 | 404.7 / 358.2 / 1390.4 |
| `window600_fixedguard` | 2026-10-05 | 600 s window with setpoint/target history, 3 scenarios per cell, guard per disturbance type plus a per-scenario cap, 3 candidates | 3 x 3 | 0 | $0.32 | 533.4 / 478.7 / 1583.0 (seed) |
| `window600_guardschedule` | 2026-10-05 | Guard loose in gens 1-2, tighter in 3-4 and from 5; failure traces of non-promoted candidates in the prompt | 4 x 3 | 1 | $0.42 | 231.5 / 247.5 / 1339.3 |
| `window600_onechange` | 2026-10-05 | Seeded with `window600_guardschedule`'s champion; one targeted change per candidate | 3 x 3 (gens 5-7) | 0 | $0.11 | 231.5 / 247.5 / 1339.3 (seed) |
| `window600_measured` | 2026-10-05 | Seeded with `window600_guardschedule`'s champion (`--from`); lessons only from promoted candidates, measured record of every tried change in the prompt | 3 x 3 | 0 | $0.21 | 231.5 / 247.5 / 1339.3 (seed) |
| `window600_high` | 2026-10-05 | Seeded with `window600_measured`'s champion, inheriting its 9 measured attempts; reasoning effort **high** (gens 1-2, then continued for gens 3-4) | 4 x 3 | 4 | $0.63 | **206.3 / 214.9** / 1199.2 |

Baselines on the same batteries: fixed recipe 533.4 / 478.7 / 1583.0, MPC 203.7 / 193.8 / 1123.6,
oracle MPC 192.9 / 191.1 / 1110.9.

## Notes

- `window600_high` champion after each promotion (dev / held-out; beyond only computed at the end of each
  invocation): gen 1 230.3 / 226.2, gen 2 227.4 / 229.2 (beyond 1181.4), gen 3 212.4 / 221.0, gen 4 206.3 /
  214.9 (beyond 1199.2).
- The window-50 runs' logged scores (in their `trials.jsonl` and `final_report.md`) are on the
  old battery (50 s window, one scenario per cell) and are not comparable with the 600 s runs;
  the table's re-scored values are.
- `window600_guardschedule` and `window600_onechange` were one trainer folder and are split by
  generation. `window600_onechange` continued from gen 1's champion, so its numbering starts at
  gen 5 and its prompts also contained `window600_guardschedule`'s lessons.
- Up to `window600_onechange`, when no candidate was promoted the trainer still saved the best
  non-promoted candidate's lessons. These were written before scoring and several describe
  changes that made the score worse (e.g. averaging the feed-load estimate), so the lessons in
  these runs' `context_report.jsonl` are hypotheses, not verified findings. From the next run
  on, lessons are kept only from promoted candidates, and the trainer records every other
  candidate as a measured line in `trials.jsonl` (`champion_score`, `biggest_gain`,
  `biggest_loss`) that the prompt lists for the whole run.
