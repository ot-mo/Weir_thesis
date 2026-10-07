# Wier Thesis: LLM Heuristic Learner as an Industrial Supervisory Controller

Master's thesis testbed exploring whether an LLM, used **offline** as a heuristic
program-synthesis engine, can produce deterministic supervisory control logic
that approaches the performance of more principled controllers (e.g. TD-MPC)
used in mining process control — while remaining human-readable, auditable,
and security-checkable in a way a learned black-box policy is not.

## Architecture: 3 layers

```
 Layer 3 (offline, LLM)        Layer 2 (online, deterministic)    Layer 1 (online, deterministic)
 ─────────────────────         ────────────────────────────       ──────────────────────────────
 DeepSeek reads logs +    -->  supervise(telemetry, setpoint, --> PIDController tracks the
 failure-point catalog,        nominal) -> new setpoint(s) +      active setpoint against the
 proposes new supervisor       anomaly flag(s), every macro       plant every fast timestep
 source code                   cycle (~3s)                        (0.1s)
      |                             ^
      v                             |
 security check (AST          hot-loaded from
 denylist + restricted        current_supervisor.py
 exec + timeout)              at process start
      |
      v
 evaluated on a fixed
 fault-injection battery,
 promoted only if it beats
 the champion (elitist)
```

- **Layer 1 — PID** ([PID.py](PID.py)): a standard `PIDController` (anti-windup via
  integral back-off) driving each plant's actuator(s) every fast timestep. Never
  regenerated or touched by the LLM.
- **Layer 2 — deterministic supervisor**: a plain Python function,
  `supervise(...)`, hot-loaded from a `current_supervisor.py` file and run every
  macro cycle (~3s) inside the live simulation. It has no network access and
  makes no LLM calls at runtime — it's just thresholds/heuristics over a
  telemetry window, deciding whether to flag an anomaly and what setpoint(s) to
  use next.
- **Layer 3 — offline LLM learner**: run manually, *never* from the live sim. It
  reads the current supervisor's source, a compact performance report across a
  fixed battery of fault-injection scenarios, and a running catalog of past
  failure points, then asks DeepSeek to propose a new `supervise` implementation.
  Every candidate must pass a security check and strictly improve on the
  incumbent (elitism) before being promoted.

This separation means the LLM's cost, latency, and reliability never touch the
real-time control loop — its only job is to author code that a fast,
deterministic layer then executes.

## Two testbeds

| | Single-tank (SISO) | Two-tank cascade (MIMO) |
|---|---|---|
| Plant | [tank_sim.py](tank_sim.py) | [two_tank_sim.py](two_tank_sim.py) |
| Live entrypoint | [LeakyTanke.py](LeakyTanke.py) | *(no live entrypoint yet — trainer/benchmark only)* |
| Offline trainer | [train_supervisor.py](train_supervisor.py) | [train_supervisor_two_tank.py](train_supervisor_two_tank.py) |
| Benchmark vs. PID-only | [benchmark_baselines.py](benchmark_baselines.py) | [benchmark_two_tank.py](benchmark_two_tank.py) |
| Generated supervisors | `generated_supervisors_leaky_tank/` | `generated_supervisors_two_tank/` |
| Supervisor signature | `supervise(telemetry_window, active_setpoint, nominal_target)` | `supervise(telemetry_window, active_setpoints, nominal_targets)` (per-tank dicts) |

**Single-tank**: one `LeakyTank` with a pump actuator and an unmeasured leak
disturbance. The simplest possible testbed for the 3-layer pattern.

**Two-tank cascade**: Tank 1 drains via gravity into Tank 2, so a fault in
either tank measurably propagates to the other (confirmed empirically — a
tank1-only fault alone swings tank2's level by over 2m with zero fault of its
own). Each tank has its own PID/actuator; the supervisor's job is genuine
cross-loop coordination, not two independent single-loop controllers. This is
the first step toward the multivariable, coupled dynamics real mining unit
operations exhibit.

## Security sandbox

All LLM-generated `supervise` code passes through [supervisor_security.py](supervisor_security.py)
before ever running against real telemetry:

1. **`check_source`** — static AST check: no imports, no `exec`/`eval`/`open`,
   no dunder/attribute sandbox-escape tricks, exactly one top-level `def
   supervise(...)` with the required signature.
2. **`safe_exec_supervisor`** — executes in a restricted namespace with a small
   explicit set of safe builtins (arithmetic, comparisons, `math`/`statistics`)
   instead of Python's real `__builtins__`.
3. **`call_with_timeout`** — every invocation (including the one-time load) runs
   in a daemon thread with a wall-clock timeout, since Windows has no
   `signal.alarm` and a runaway candidate (`while True: pass`) must not hang
   the caller.

[test_supervisor_security.py](test_supervisor_security.py) exercises this
adversarially (import injection, `open()`, a `__class__.__bases__` sandbox
escape, an infinite loop).

## Fitness function & anti-gaming guards

Candidates are scored across a fixed battery of fault-injection scenarios
(no-fault baseline, single leaks of varying onset/magnitude/duration, sensor
noise, simultaneous faults). The score combines tracking error (IAE), safety
violations, missed anomalies, false positives, exceptions/timeouts, and a
restoration gap (did the setpoint return to nominal after the fault cleared?).

Two things learned the hard way and now built in:

- **A false positive in a scenario with zero fault ever is penalized far more
  harshly** than one during genuine fault ambiguity — otherwise a supervisor
  can "solve" hard scenarios by flagging anomalies constantly and only pays a
  cheap, uniform price for it.
- **A candidate is only promoted if it doesn't regress any individual
  scenario beyond tolerance**, even if the *average* score improves. Averaging
  across a scenario battery otherwise lets a candidate win in aggregate by
  badly breaking one scenario (especially a provably fault-free one) while
  gaining disproportionately elsewhere — a composite-score exploit
  structurally identical to reward hacking in RL.

## Running it

```bash
# Live single-tank simulation (opens a plot window)
python LeakyTanke.py

# Offline trainer (makes real, billed DeepSeek API calls)
python train_supervisor.py [num_trials]        # single-tank
python train_supervisor_two_tank.py [num_trials]  # two-tank
python train_supervisor_four_tank.py [num_generations] [--effort none|low|high|max] [--run NAME]  # PC-Gym four-tank, 4 candidates/generation; --run keeps a separate experiment seeded from gen_0
python train_supervisor_four_tank.py --report      # four-tank report only, no API calls
touch STOP_TRAINING                                # four-tank: stop cleanly after the current generation

# Compare the current trained supervisor against a PID-only baseline
python benchmark_baselines.py     # single-tank
python benchmark_two_tank.py      # two-tank

# Security/sandbox tests
python test_supervisor_security.py
```

Requires a `.env` file with `DEEPSEEK_API_KEY` set (only needed for the
trainer scripts — the live sim and benchmarks make no network calls).

## PC-Gym four-tank benchmark

[pcgym_four_tank.py](pcgym_four_tank.py) runs our two-tank supervisor
interface against PC-Gym's built-in `four_tank` model (Johansson's classic
quadruple-tank process) instead of our own plant — a richer, better-known MIMO
benchmark with real cross-coupling (each pump feeds its own tank directly and
the *other* loop's tank indirectly, through a delayed path), closer to a
multivariable circuit like a ball mill than our direct two-tank cascade.

Setup: `pip install --user pcgym` (installing without `--user` fails on this
machine with a permissions error against the system Python's `Scripts`
folder). The plant is PC-Gym's `four_tank` model class integrated directly
with explicit Euler — `pcgym.make_env` is bypassed because fault injection
silently had no effect through its wrapper (see the module docstring).

```bash
python pcgym_four_tank.py
```

The supervisor keeps the same interface (`supervise(telemetry_window,
active_setpoints, nominal_targets)`), where `tank1`/`tank2` are the h1/h2
level loops and each tank's `pump_effort` is the output of the loop
regulating it.

**Testbed corrections (2026-09-29).** A plateau at 36,300 after ~20 trials
turned out to be caused by the testbed, not the LLM — the champion was within
~7% of the best score any supervisor could reach there:

- *Decision cadence:* decisions every 50 s forced ≥51 missed + ≥51 false-positive
  steps per fault event. The supervisor now decides every 10 s on overlapping
  50-sample windows, with window-relative time; fault onsets sit off the
  decision grid in both dev and validation.
- *Loop pairing:* with γ₁ = γ₂ = 0.2 the diagonal relative gain is −0.07, so
  Johansson (2000) pairs v1↔h2, v2↔h1. The diagonal pairing starved the
  leaking tank (tank 1 leak → loop 2 cut pump 2 → tank 3, tank 1's main feed,
  drained), leaving 171 safety violations no setpoint policy could remove.
  The loops are now cross-paired and retuned as PI (Kp = 40, Ki = 0.3); PID-only
  has zero violations on every scenario.

The trainer now samples 4 candidates per generation at temperature 1.0 and
gives the LLM a plant-engineer-level description of the process plus
per-decision traces of the champion on its worst scenarios.

| Supervisor (corrected testbed) | Dev | Held-out |
|---|---|---|
| PID-only / gen_0 seed | 64,865 | 69,569 |
| Old champion, transplanted without retraining | 10,777 | 14,941 |
| gen_1 (1 generation) | 6,127 | 7,100 |
| gen_2 (2 generations) | 4,627 | 3,600 |
| Perfect-detection oracle | 2,635 | 2,609 |

The gen_2 champion has zero false positives on the fault-free scenario; most
of its remaining cost is in `both_leaks`, where one tank's leak partly masks
the other's through the cross-coupling.

## Four-tank setpoint coordination (grinding-circuit rehearsal)

The thesis goal document asks how an LLM-synthesized supervisor compares with a
model-based predictive supervisor at *coordinating setpoints under disturbances*
(RQ1), and how both degrade beyond the development range (RQ2).
[four_tank_coordination.py](four_tank_coordination.py) rehearses that on the
quadruple-tank process:

| Grinding circuit | Four-tank analog |
|---|---|
| P80 on target | production rate (tank 1 + tank 2 outflow) |
| Sump level stable | h2 inside a band |
| Circulating load within limits | upper-tank levels below a limit |
| Fresh feed / ore density / % solids | feed in/outflow / pump gain / valve split disturbances |

The supervisor moves only the two PI setpoints (no anomaly flags). It is called
every 10 s with the last 10 minutes of telemetry (levels, pump voltages,
production, and the setpoints and target active at each sample). Scenarios
cover the goal document's factors (disturbance kind × step/ramp/sine × inside or
beyond the development range, three scenarios per cell); metrics are production
IAE, constraint-violation time, setpoint total variation and recovery time.
[mpc_supervisor.py](mpc_supervisor.py) is the model-based predictive baseline
(online disturbance estimate). It comes in three variants: the original untuned controller, the
controller tuned on the development battery with a score-aligned cost (`tune_mpc.py`), and the tuned
controller with known current disturbance as a reference (not an upper bound).

```bash
python benchmark_coordination.py [per_cell]   # fixed recipe vs untuned / tuned / known-disturbance MPC, no API calls
python tune_mpc.py [budget]                   # tune the MPC on the dev battery (default 40 configurations), no API calls
python stress_test_coordination.py [--runs RUN ...]   # noise, plant mismatch, analyser delay, telemetry faults, no API calls
python evaluate_sealed_test.py --unseal "REASON" --runs RUN ... --baselines   # the sealed test battery, once, logged
python analyze_protocol.py --scores CSV --runs RUN ...   # pre-registered statistics (--dry-run on validation batteries)
python train_supervisor_coordination.py [num_generations] --run NAME [--from RUN] [--model deepseek-flash|gpt-6-luna|gpt-6.1-sol] [--effort low]  # LLM meta-supervisor (billed)
python train_supervisor_coordination.py --report --run NAME                             # champion vs baselines, no API calls
```

Every run is named and has its own folders, `generated_supervisors_coordination/NAME/`
and `results/coordination/NAME/`; a new name starts from the fixed recipe (or from
another run's champion with `--from RUN`, inheriting that run's measured record of the changes
already tried on the champion), an existing name continues.
[results/coordination/README.md](results/coordination/README.md) lists all runs with
their setup, cost and champion scores.

[train_supervisor_coordination.py](train_supervisor_coordination.py) is a copy of
the four-tank trainer (which stays as it is for the leak task): the LLM writes
`supervise(telemetry_window, active_setpoints, objectives)`, which returns new
setpoints only, passes the same security gate and is promoted on the development
battery if it improves the average without making any disturbance type worse on
average (or wrecking a single scenario). That regression guard is loose in
generations 1-2 and tightens in 3-4 and from 5 on, so an early candidate that is
much better overall but worse on one scenario still gets promoted and its weak
scenario then shows up in the next prompt's traces. The prompt also shows, for up
to two non-promoted candidates of the previous generation, the decision trace of
the scenario each lost most on. Each candidate must make one targeted change
to the champion (one mechanism, the rest of the code kept), and the share of the
champion's lines it kept is logged: in the first guard-schedule run, before
this rule, candidates kept 16-65% of the champion and added 107-272 lines. The
model's own lessons (cause-effect relations) are kept only from promoted
candidates; every other candidate is recorded by the trainer as one measured line
(its change, average against the champion, scenario gained and lost most on),
and the prompt lists all of them for the run so failed changes are not repeated.
The beyond-range battery is never shown to the LLM and only appears in the report,
next to the baselines on identical scenarios.

### Results

All scores on the same batteries (42 development / 42 held-out development / 36 beyond the
development range, 600 s window); lower is better. The beyond-range battery is never shown to
the LLM.

| Controller | Development | Held-out | Beyond range |
|---|---|---|---|
| Fixed recipe (PID loops only; the seed) | 533.4 | 478.7 | 1,583.0 |
| LLM champion, `window50_run2` (50 s window) | 226.3 | 242.2 | 1,276.9 |
| LLM champion, `window600_guardschedule` (600 s, reasoning effort low) | 231.5 | 247.5 | 1,339.3 |
| LLM champion, `window600_high` (600 s, reasoning effort high) | 206.3 | 214.9 | 1,199.2 |
| MPC, untuned (original) | 203.7 | 193.8 | 1,123.6 |
| **MPC, tuned on the development battery** | **133.9** | **157.2** | **732.3** |
| MPC, tuned, known current disturbance | 118.4 | 144.0 | 701.6 |

The best beyond-range score among the LLM champions is still `window50_run1`'s 1,189.8 (its
development score is 255.6). The runs index has every run.

The earlier impression that the LLM champion nearly matched MPC came from an untuned baseline.
Its cost penalised the squared size of a constraint violation while the score counts every second
of it, so a 1 mm violation was nearly free. `tune_mpc.py` gives the MPC a score-aligned cost and a
tuning budget comparable to the LLM's: 40 configurations on the development battery, against about
40 candidates in the champion's lineage. The tuned MPC is clearly better on all three batteries.

### Protocol

These numbers come from a single lineage of runs, steered by hand, on batteries that were looked
at after every redesign of the loop. [results/coordination/PROTOCOL.md](results/coordination/PROTOCOL.md)
fixes everything before the confirmatory runs:
- the method;
- 8 independent runs of 6 generations from the seed;
- the tuned MPC as the comparator;
- a sealed test battery of 183 scenarios, with graded amplitude levels and unseen periods and
  combinations (`coordination_test_battery.py`), opened once by `evaluate_sealed_test.py`;
- the statistics (`analyze_protocol.py`).

Every supervisor now runs behind a fixed safety wrapper in the test bed: NaN and range checks, a
0.12 m-per-call rate limit, and a hold on invalid input or output.
[results/coordination/stress_tests.md](results/coordination/stress_tests.md) shows the
controllers under sensor noise, plant mismatch, analyser delay and telemetry faults. These results
are exploratory, on the validation batteries:
- **Sensor noise.** The tuned MPC is fragile: +45 % at 1 mm and +151 % at 3 mm, because of its
  fast disturbance estimator. The LLM champion changes by -1 % and +6 %.
- **Plant mismatch.** With every plant parameter off by up to 10 %, all model-based controllers
  degrade by 120-470 %. None of them has integral action on the production error, so they believe
  production is on target when it is not.
- **Analyser delay.** Only the LLM champion reads the production field, so only it is affected
  by a delayed or frozen analyser (+11-14 %).
- **NaN on h3.** The wrapper holds the setpoints from the fault onwards. That is safe but crude:
  +14-203 % for every controller.

### Why the window is 600 s

The supervisor is stateless: it is reloaded for every call and its only memory is the
telemetry window. With the earlier 50 s window it could not tell an oscillating disturbance
(periods 200-500 s) from a ramp or a step, and it could not see its own setpoint changes or a
production-target change settling (with the retuned PI loops, about 90-160 s to within 2 % and
270-400 s to within 0.5 % for a 5-10 % target change). In
the 50 s runs, champions read the target-change transient as a disturbance and chattered their
setpoints. The 600 s window covers more than one oscillation period and the full settling time,
and each sample now also carries the active setpoints and production target. Three scenarios
per cell instead of one were introduced at the same time, so that one noisy scenario weighs
less in the score and in the regression guard.

### What moved the 600 s champion

The 600 s runs changed one part of the training loop at a time (details in the runs index):

1. `window600_fixedguard`: no promotion. Every candidate that beat the seed's average (best 258
   against 533) was rejected by the regression guard, so the model kept seeing only the seed.
2. `window600_guardschedule`: a guard that is loose in the first generations gave the first
   promotion, 231.5. The later candidates rewrote the whole supervisor (keeping 16-65 % of it)
   and each fixed one scenario while breaking others.
3. `window600_onechange`: with one targeted change per candidate, candidates kept 84-98 % of
   the code, but all nine changed the load estimate the same way (averaging it), which fixed
   oscillations and broke steps. The lessons saved in those runs came from candidates that had
   made the score worse and pointed back at that change.
4. `window600_measured`: lessons kept only from promoted candidates, and every tried change
   recorded by the trainer with its measured effect. The model moved on to oscillation-aware
   estimators (best 241.5) but nothing was promoted. Its first generation repeated old
   failures because a new run started without that record, so `--from` now passes it on.
5. `window600_high`: the same loop at reasoning effort high, starting with the inherited
   record. Four promotions in four generations, 231.5 to 206.3: a pump-gain estimate corrected
   for upper-tank storage, a feedback trim on the tank-1 setpoint from the measured production
   error, that trim made predictive, and a shorter hold after the supervisor's own setpoint
   changes. About 80k output tokens per request against 16-40k at effort low; 12 requests,
   about $0.63.

High effort and the inherited record were introduced in the same run, so this single run does
not separate their effects. Development improved faster than held-out over the last two
generations (the gap grew from about 2 to about 9 points), which is worth watching for
overfitting to the development battery.

## Status / open threads

- Single-tank supervisor has gone through ~60 generations; current champion
  detects and recovers from all battery scenarios and restores to nominal
  after a fault clears.
- Two-tank supervisor reliably solves single-tank-at-a-time faults, but
  simultaneous faults on both tanks remain unsolved: every attempt so far
  that improves joint-fault detection breaks robustness to sensor noise, and
  the model has been repeating near-identical proposals across trials rather
  than exploring new approaches — a likely local-optimum/search-diversity
  issue worth addressing before more trials.
- Four-tank setpoint coordination: the exploratory runs are done, and the best LLM champion
  (`window600_high`) scores 206.3 / 214.9 / 1,199.2 against the tuned MPC's 133.9 / 157.2 / 732.3.
  The confirmatory runs (`protocol_run1`-`8`) under the registered
  [protocol](results/coordination/PROTOCOL.md) have not started. After them, the sealed test
  battery is evaluated once and analysed with `analyze_protocol.py`. The planned ablations (a prompt
  without plant equations, and best-of-N one-shot) are exploratory and not implemented yet.
- No TD-MPC baseline yet. The comparison with Weir's TD-MPC needs access to their simulator and
  controller, and a decision on whether plant details may be sent to the LLM provider. A
  run-of-mine grinding-circuit model (le Roux et al. 2013) is the fallback test bed.

