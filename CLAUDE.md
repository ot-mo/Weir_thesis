# Working conventions

- Commit changes as you go while working, not just at the end of a session. The user wants a git history that reflects the actual steps taken (e.g. one commit per logical change: a refactor, a bug fix found during verification, a cleanup pass), not one giant squashed commit at the end.
- Push to origin/main automatically after each commit, without asking for confirmation first. Confirmed 2026-09-22.

# Common commands

- Run the live sim (opens a plot window): `python LeakyTanke.py`
- Run the live sim headlessly / from an agent, without blocking on the plot window: `MPLBACKEND=Agg python LeakyTanke.py`
- Run the offline Layer-3 trainer (makes real, billed DeepSeek API calls — confirm with the user first): `python train_supervisor.py [num_trials]` (defaults to 10 trials if omitted)
- Run the four-tank (PC-Gym) trainer (billed DeepSeek calls, 4 per generation plus retries — confirm with the user first): `python train_supervisor_four_tank.py [num_generations] [--effort none|low|high|max] [--run NAME]` (`--run NAME` = separate experiment with its own candidates/lessons/logs, seeded from gen_0; `--effort none` = thinking off; defaults to 4 generations at reasoning effort "low": measured ~28k output tokens/request vs ~61k at "high", and output is ~97% of the cost). DeepSeek peak pricing (2x) is 08:00-12:00 and 03:00-06:00 Swedish time on weekdays.
- Stop a running trainer cleanly after its current generation: create an empty `STOP_TRAINING` file in the repo root (e.g. `touch STOP_TRAINING`). Never kill the process to stop it — requests already sent keep generating and are billed anyway. Report only, no API calls: `python train_supervisor_four_tank.py --report`
- Run the supervisor security/sandbox tests: `python test_supervisor_security.py`
