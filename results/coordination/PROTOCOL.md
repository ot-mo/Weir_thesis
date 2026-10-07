# Pre-registered protocol: LLM-synthesized supervisor vs MPC on the four-tank coordination test bed

Status: **registered, version 2** (see Changelog). The commit that adds the current version fixes the protocol. Nothing listed under
"Frozen" may change between that commit and the final analysis. Any change creates a new protocol
version (a new commit of this file, with a changelog entry) and restarts the runs. Runs started
under an earlier version are reported, not discarded.

## Why a protocol

Before this protocol, the training loop was redesigned about a dozen times while looking at the
development, held-out and beyond results. The best champion (`window600_high`) came out of a
hand-steered chain of runs, not from one fixed method. Those batteries now serve as validation
sets. This protocol fixes the method, the number of runs, the comparator, the test battery and the
statistics before any result exists. See the council review summarized in the commit history of
2026-10-07.

## Research questions and hypotheses (goal document)

- **RQ1 / H0,1:** on disturbances inside the development range, the LLM-synthesized supervisor
  and the model-based predictive supervisor perform the same (mean composite score).
- **RQ2 / H0,2:** performance degrades with disturbance amplitude beyond the development range
  at the same rate for both controllers.
- **C3:** variance between independently generated policies.

## Frozen

**Test bed:** `four_tank_coordination.py` as of the registration commit.
- 600 s window, called every 10 s, 1200 s episodes.
- PI level loops (`PI_GAINS`, cross-paired): h1 loop Kp 15 V/m, Ti 133 s; h2 loop Kp 40 V/m, Ti 200 s.
  These are the lowest load-disturbance IAE with Ms <= 1.6 from `tune_pi_coordination.py`, giving
  Ms 1.56.
- `SCORE_WEIGHTS` = production IAE 1 per L, h2-band violation 2 per s, upper-level violation 2 per
  s, safety violation 10 per s, setpoint travel 100 per m, exception 1000 each. These were marked
  provisional earlier and are frozen here.
- Safety wrapper with `MAX_SETPOINT_STEP` = 0.12 m per call.

**Batteries:**

| Battery | Seed | Role |
|---|---|---|
| Development | 1 | 42 scenarios. Drives promotion and is visible in the prompt. |
| Held-out | 2 | 42 scenarios. Shown to the LLM only as the dev-vs-held-out gap. |
| Beyond | 3 | 36 scenarios. Report only. |
| Sealed test | 7351 | `coordination_test_battery.py`, 183 scenarios, fingerprint `867c37cfc2af1bbc4b64f59c6af949d9eb354bcaa02c1ea52f95a34cbd9747e0`. Used once, in the final evaluation. |

**Sealed test battery parts:**

| Part | Scenarios | Content |
|---|---|---|
| `dev` + `nominal` | 42 | Development range, new seed |
| `x1.25`, `x1.5`, `x2` | 36 each | Amplitudes 1.25, 1.5 and 2 times a development draw |
| `unseen_period` | 24 | Sine periods 100–180 s and 550–800 s |
| `unseen_combination` | 9 | Feed, pump and split together |

**Method (the LLM side):** `train_supervisor_coordination.py` as of the registration commit, with:
- model `deepseek-flash`, reasoning effort **high** (256k reply cap), 3 candidates per generation;
- **6 generations per run**, each run starting from the fixed recipe (`supervisor_gen_0.py`), never
  `--from`;
- guard schedule (loose in generations 1–2, medium in 3–4, strict from 5), one targeted change per
  candidate, measured record of every tried change, lessons only from promoted candidates, failure
  traces, and the held-out gap in the prompt.

**Runs:** **N = 8** independent runs, `protocol_run1` … `protocol_run8`:

    python train_supervisor_coordination.py 6 --run protocol_runK --effort high

Runs may run in parallel. A run that fails technically (API errors) is resumed under the same name
until it has 6 generations. It is never replaced or dropped. A run stopped for any other reason is
reported as stopped. Estimated cost: about $1 per run, so about $8 in total.

**Policy per run:** the run's final champion, `generated_supervisors_coordination/protocol_runK/current_supervisor.py`
after generation 6. It is not chosen by held-out or any other score ("the last champion counts").

**Comparators (baselines):**
- **Primary: `mpc_tuned`.** The MPC of `mpc_supervisor.py` with the parameters in
  `results/coordination/mpc_tuned_params.json` (as of commit 1411e99): score-aligned cost, 200 s
  horizon, estimator gain 0.774, headroom weight 27.39, margin 0.0128 m, travel price ×3.78. It
  was chosen by `tune_mpc.py` from 40 configurations on the development battery, a budget
  comparable to the roughly 40 candidates in the `window600_high` champion's lineage.
- Secondary: `mpc_untuned` (the original MPC).
- Reference: `fixed_recipe`, and `mpc_known_disturbance` (the tuned MPC with known current
  disturbance; not an upper bound, it loses to `mpc_tuned` on 19 of 120 validation scenarios).

## Final evaluation and analysis

After all 8 runs are complete, run exactly once:

    python evaluate_sealed_test.py --unseal "final protocol evaluation" --runs protocol_run1 ... protocol_run8 --baselines
    python analyze_protocol.py --scores results/coordination/sealed_test/scores_<stamp>.csv --runs protocol_run1 ... protocol_run8

The access log (`results/coordination/sealed_test/access_log.jsonl`) is committed. Any further
look at the test battery is logged with a reason and reported in the thesis.

**Primary analyses** (as implemented in `analyze_protocol.py`, bootstrap B = 10000, seed 7):

1. **H0,1.**
   - Statistic: the mean paired difference in composite score, LLM minus `mpc_tuned`, over the 8
     policies and the 42 development-range test scenarios.
   - Interval: 95 % CI from a hierarchical bootstrap (resample policies, then scenarios).
   - Rejecting H0,1: the CI excludes 0.
   - Parity: the LLM is called equivalent to the MPC only if the 90 % CI lies inside ±10 % of
     `mpc_tuned`'s mean (TOST). Failing to reject H0,1 does not establish equivalence.
2. **H0,2.**
   - Statistic: the slope of mean log(1 + score) against amplitude level (1, 1.25, 1.5, 2;
     disturbance scenarios only), LLM (mean over policies) minus `mpc_tuned`.
   - Interval: 95 % CI from the same bootstrap, with scenarios resampled within each level.
   - Rejecting H0,2: the CI excludes 0.
3. **C3.**
   - Per-policy mean composite score on the development-range test scenarios: median, IQR and
     range.
   - The between-policy SD, with a 95 % CI from the chi-square distribution. A percentile
     bootstrap of an SD cannot exceed the spread in the sample and is biased low for few policies;
     it is reported as secondary. With N = 8 the chi-square interval spans about 0.66 to 2.04 times
     the estimate.
   - The number of runs without any promotion.

**Secondary analyses** (reported, Holm-corrected where marked):
- Per-metric paired differences on the development range: production IAE, band, upper and safety
  violation seconds, setpoint travel, saturation, recovery, wrapper interventions. Bootstrap
  p-values, Holm-adjusted.
- LLM/MPC score ratios with CIs on `unseen_period` and `unseen_combination`.
- Results per disturbance kind and pattern (descriptive).

**Exploratory, not confirmatory:**
- **Stress tests** (`stress_test_coordination.py`, on the validation batteries): sensor noise,
  plant mismatch, analyser delay and telemetry faults. Run before registration on the
  `window600_high` champion and the baselines, and re-run for v2 with the retuned loops
  (`results/coordination/stress_tests.md`). They may be repeated on the protocol policies.
- **Planned ablations**, each run under its own name after the protocol runs:
  - a prompt without the plant equations and parameters (transfer to a plant without a white-box
    model);
  - best-of-18 one-shot samples from the seed without the feedback loop (does iteration matter).

  They need a small trainer change, committed before they run, and are reported as exploratory.

## Known limitations, stated in advance

- The prompt gives the exact plant equations and parameters, and measurements are noise-free.
  Results may not transfer to a plant without a white-box model (see the stress tests and the
  planned ablation).
- The four-tank process is a rehearsal for the grinding circuit. Production is an algebraic
  function of the levels, with no analyser delay in the nominal test bed.
- The MPC holds one setpoint move over its horizon (move blocking) and estimates disturbances as
  additive inflows.
- The held-out gap is part of the method's prompt, so the held-out battery is not a clean test.
  Only the sealed battery is.

## Changelog

- v1 (2026-10-07): registered.
- v2 (2026-10-07): before any protocol run and before any access to the sealed battery, the PI level
  loops were retuned for robustness. The previous gains (Kp 40, Ti 133 s on both loops, copied from the
  leak test bed) had Ms 2.98 and 40 % overshoot, while the real plant's loops can be assumed to be well
  tuned. Because the plant changed, everything that depends on it was redone:
  - the MPC was re-tuned with the same procedure (config 31, dev 158.8; was config 2, 133.9);
  - the baselines and stress tests were re-run, and the analysis dry run was repeated;
  - the prompt now states the new gains and the re-measured loop transient.

  The battery definitions, score weights, method, N, generations and statistics are unchanged.
