# Thesis guide

Written 2026-11-16 from the state of both repositories on that day:

- `ot-mo/Weir_thesis` `main` (last thesis commit `c382791`, 2026-10-31)
- `SentianAI/LLM-Synthesized-Supervisory-Control` `main` (PR #37 merged), plus the unmerged branch
  `feed-noise` (2026-11-13: noise training, feed fluctuations and the VM-week summary
  `lib/llm-supervisor/docs/vm_week_2026-11-04_13.md`)

This guide is not prose for the thesis. For each chapter it says what the chapter is for, what goes in
it (with the file or PR that holds each number or figure), what we learned, and what to do with the
text that is there now. Paths starting with `docs/` are in the mill repo under `lib/llm-supervisor/`.

---

## 1. The short version

**The thesis has changed shape.** The current draft (`main.tex`) was written when the tank test beds
were the results and the grinding circuit was a setup section with a TODO. Since then the grinding
circuit has become the thesis: 15+ training runs, a fair comparison with Weir's deployed TD-MPC at
three decision intervals, noise studies, a normalised score and a sealed test battery. The draft's
abstract, introduction, discussion and conclusions still lead with the tank results ("72-96 %
reduction", "67 % worse than a tuned MPC"), and the mill results sit in one paragraph of the Method
chapter.

**Recommendations, in order of importance**

1. **Make the grinding circuit the core of the thesis.** Two new chapters: *The grinding circuit and
   the comparison* (setup) and *Results on the grinding circuit*. The LaTeX on this branch already
   has both, with the existing mill text moved into them and a section skeleton for the results.
2. **Merge the two tank chapters into one chapter, *Developing the method on tank processes*, at about
   half their current length.** Keep the lessons that shaped the method (specification gaming, a sound
   test bed and an oracle, the reasoning ablation, the guard schedule and the measured record, the
   tuned-MPC comparison and the loop dependency). Move the fault-detection score, the long run table
   and the four-tank protocol to an appendix. Reasoning in Section 4.5.
3. **Drop the four-tank protocol as a forward-looking promise.** Its eight runs were never made and
   will not be; the work moved to the mill, where the real comparator is. Say so in one paragraph.
   On this branch its text has moved from the Method chapter to the end of the coordination chapter.
4. **Decide and register the mill protocol now, then run it.** H0,1 and H0,2 can only be answered by
   the registered runs on the sealed battery. Everything so far is exploratory: the champions were
   selected on the batteries they are compared on. The protocol's OPEN items are listed in Section 3.
   Without the protocol runs, the thesis has to present the comparison as exploratory evidence and
   say plainly that the hypotheses were not tested.
5. **Rewrite the abstract, introduction (contributions, outline), discussion and conclusions around
   the mill** once the results chapter has its numbers. Do it last; the drafts are listed below.
6. **Report two (three) measures everywhere**: our score, the TD-MPC's reward, and the normalised
   score. The thesis has to explain why they disagree on the sump level (Section 6.4).
7. **Add noise as its own axis** (none, measurement, feed, both). It is the most interesting
   result so far: noise reverses the noise-free ranking, and the reason can be pointed to in one line
   of code. That is the interpretability argument made concrete.

---

## 2. Proposed structure

| # | Chapter | Status now | Proposal | Pages (rough) |
|---|---|---|---|---|
| - | Abstract | tank-first, TODO for mill | Rewrite last, mill-first | 1 |
| 1 | Introduction | good RQs and hypotheses; contributions and outline tank-first | Keep motivation and RQs; rewrite contributions, delimitations, outline | 4 |
| 2 | Background | short, three TODOs, a fault-detection section | Add grinding-circuit control; expand TD-MPC; drop fault detection | 6-8 |
| 3 | Method (the synthesis framework) | good, but mixes tank and mill versions and holds the mill setup and the four-tank protocol | General framework as used on the mill; tank-era differences in one paragraph; mill protocol | 10-12 |
| 4 | Developing the method on tank processes | two chapters (toy 209 lines, coordination 485 lines) | Merge, halve; lessons first | 8-10 |
| 5 | The grinding circuit and the comparison | a section of Method | New chapter (created on this branch) | 8-10 |
| 6 | Results on the grinding circuit | one paragraph and one table | New chapter (skeleton on this branch) | 15-20 |
| 7 | Discussion | tank-first | Rewrite around mill themes, keep two tank themes | 6-8 |
| 8 | Conclusions and future work | tank-first | Rewrite: answer RQ1, RQ2, C3 | 2-3 |
| A | Appendices | quadruple-tank supervisor listing | Mill champion listing, tank details, four-tank protocol, prompt excerpt, noise model table | as needed |

Why this order: the reader needs the framework (Ch. 3) before the tank chapter can explain why each
part exists, and the tank chapter is the honest history of how the method was built. The mill setup
then stands on its own, and the results chapter can be read as the answer to the research questions.

An alternative is to put the whole tank chapter in an appendix and keep only a two-page "lessons from
development" section in the Method chapter. Choose that if the page budget is tight. I recommend
the merged chapter, because two of its findings (the tuned comparator, and noise reversing the
ranking) reappear on the mill and make the mill results more convincing.

---

## 3. What has to happen before the results chapter can be finished

These are decisions and runs, not writing. They come from `docs/PROTOCOL.md` (draft, OPEN items) and
section 11 of `docs/vm_week_2026-11-04_13.md` (branch `feed-noise`).

| Item | Options / what is known | Who decides |
|---|---|---|
| Prompt version of the registered runs | 5 (one champion), 6 (explore in three lineages, then exploit), 7 (6 trained under measurement noise). Evidence favours 6: every v6 champion beats both v5 protocol runs on reward on every battery, and dev spread 1.7 vs 9.2 points. | otto |
| Train under noise? Which? | Measurement-noise training (v7) makes champions insensitive to measurement noise but buys nothing against feed fluctuations; feed-fluctuation training is untested. | otto (+ Kaige) |
| Generations per run | Pilot at 300 s still improved at gen 12 (67.0); v6 runs are 12 gens. 12 is the natural choice. | otto |
| N runs, sealed battery sizes | N = 8, 216 sealed scenarios, ~12-16 h + 2-4 h of evaluation on the VM. ~$3.5 per run (v6 runs cost $3.23-3.62), so ~$28 for eight. | otto |
| Equivalence margin | ~5 % of score / 0.02 reward proposed; Kaige asked for an explanation of "negligible". | otto + Kaige |
| Noise sizes | Measurement noise sizes are our guesses; feed fluctuation sizes for ore density and solids await Kaige. | Kaige |
| Score vs reward on the sump level | Report both (current plan), or reconsider the level objective. | otto + Kaige |
| Merge `feed-noise` into `main` | One PR covers it. The thesis should cite merged docs. | otto (opens PRs) |

Rough timeline if the protocol is registered this week: 8 runs on the VM at ~2.5 h each (two to
three days of VM time), then one sealed evaluation (~1 day). The results chapter can be written in
parallel from the exploratory results; the sealed-test section is filled in last.

If time runs out: present the exploratory comparison (Sections 6.2-6.6) as the result, with the
caveats in Section 6.8, and put the protocol in future work. That is a weaker but honest thesis.

---

## 4. Chapter by chapter

### Abstract

**For:** the question, the method in two sentences, the main numbers, the main caveat.

**Include:** the three-layer idea (offline LLM writes deterministic Python, runs over Weir's PID
loops); the grinding circuit and Weir's deployed TD-MPC (`autumn-night-41`) as comparator at 300 s;
the headline comparison (sealed-test results if run, otherwise the exploratory ones with "exploratory"
in the sentence); robustness beyond range and under noise; the run-to-run spread; the cost per run
(~$3-4); one sentence on the tank development work.

**Now:** tank-first, mill as a TODO. Rewrite last.

### 1 Introduction

**For:** why supervisory control of grinding circuits matters, why an LLM offline, the RQs,
hypotheses and contributions.

**Keep:** Motivation (it follows the goal document, `Måldokument-1.pdf`, closely); RQ1, RQ2, H0,1,
H0,2; C1-C3.

**Change:**
- *Contributions:* replace the tank paragraph with what the thesis actually delivers. Suggested list:
  C1-C3 as now (answered by the mill protocol); plus (a) a training loop for LLM-synthesised
  supervisors with the safeguards that made it work (Ch. 3-4), (b) a fair-comparison harness for an
  LLM supervisor and a learned world-model controller on the same simulator, interface, wrapper,
  batteries and two metrics, (c) robustness results under measurement noise and feed fluctuations.
- *Delimitations:* one simulated circuit, one operating point (the goal document asks for "several
  operating points": say we have one), noise-free main comparison, no plant deployment, one LLM
  family on the mill (Claude Opus 5.5, effort low), the TD-MPC as delivered (not retrained).
- *Outline:* follow the new chapter order.

**Learned:** nothing new; this chapter just has to stop promising the tank results as the main story.

### 2 Background

**For:** what a control engineer needs to read the thesis; the three bodies of work in the goal
document.

**Include:**
- *Supervisory control of grinding circuits* (missing now; goal document's first body of work):
  the circuit (mill, sump, cyclones, circulating load, P80), typical regulatory loops, how
  supervision is done in practice: operators, expert systems, fuzzy logic, MPC in mineral processing.
  A few standard references (e.g. Hodouin's and Wei & Craig's reviews of grinding-circuit control).
  Replace the TODO in *Supervisory process control* with this.
- *Learned controllers:* expand TD-MPC: latent model, planning horizon, value bootstrapping, reward
  design. What it can do that a rule set cannot (implicit model of the whole circuit, trained on many
  episodes) and the reverse (inspection, guarantees on what the code can do, editing).
- *LLM-guided program search:* keep (FunSearch, AlphaEvolve, Eureka, PromptPO, LBG). Add a sentence on
  quality-diversity / island models, since prompt version 6's lineages are that idea.
- *Specification gaming:* keep.
- *Statistics for paired comparisons* (short): paired designs, bootstrap intervals, equivalence
  testing (TOST), because Kaige asked what "negligible" means and the protocol uses it.

**Remove:** *Fault detection*. It serves only the leak test beds; move two sentences into Ch. 4.

### 3 Method (the synthesis framework)

**For:** the method as it runs on the mill, described generally enough to be applied to another plant
(otto's standing rule: no changes fitted to this mill).

**Keep (mostly as written):** three-layer architecture and its figure; supervisor interface
(coordination variant); security sandbox; safety wrapper; batteries and their roles; promotion and
the guard schedule; training loop; comparators (minus the four-tank MPC detail).

**Change:**
- Describe the **mill version of the loop** and give the tank-era differences in one paragraph (it
  already has that paragraph; keep it). Mill additions to describe:
  - validation check before promotion (prompt version 5, mill commit "Trainer: validation check before
    promotion");
  - prompt versions 5, 6, 7 (`trainer.PROMPT_VERSIONS`; `docs/explore_exploit.md`,
    `docs/noise_training.md`): explore in three lineages (`energy`, `level`, `quality`) for 4
    generations, choose, exploit with one candidate per large score term; v7 states the noise;
  - duplicate-candidate re-ask; prompt caching and staggered requests (cost);
  - score cache and compiled Layer 1 (only as engineering: bit-identical, 2-2.7x faster; PR #9).
- **Language models:** tanks used `deepseek-flash`; the mill uses Claude Opus 5.5 at effort low (Weir
  approved sending plant data to Anthropic, 2026-10-22). Say why the switch happened and that models
  were not compared on the mill (limitation). The TODO about "on early tests" needs either the logged
  comparison or the sentence removed.
- **Scoring:** move the fault-detection score (Eq. `eq:score`) to Ch. 4 or the appendix. Keep a
  general paragraph: weighted penalties per scenario, battery mean, lower is better.
- **Pre-registered protocol:** make it the mill protocol (`docs/PROTOCOL.md`): frozen choices
  agreed with Kaige (P80 range 180-200 µm, both at 300 s, `autumn-night-41`), N runs, policy = final
  champion, sealed battery (seed 20261109, 216 scenarios in five parts, fingerprinted, opening
  logged; PR #37), hierarchical bootstrap, co-primary score and reward, H0,2 slope over amplitude 1,
  1.25, 1.5, 2, C3 statistics, variants (60/900 s, noise). Note the deviation from the goal
  document (bootstrap instead of t-tests/mixed model) and why (few policies, non-normal, terminal
  episodes). On this branch the four-tank protocol text has moved to Ch. 4.

**Learned (for the chapter's framing):** each piece exists because something failed without it.
Point forward to Ch. 4 (tanks) and Section 6.1 (mill) for the failures.

### 4 Developing the method on tank processes (merge of `toy_examples.tex` and `coordination.tex`)

**For:** the history that justifies the method, and two results that the mill confirms. Not a second
results chapter.

**Why merge and shrink:** the tank results do not answer the RQs (they are about a rehearsal process
and, for three of four test beds, about fault detection, which is outside the RQs). The draft spends
~700 lines on them against ~100 on the mill. But they hold the lessons that made the mill work, and a
reader who sees only the mill will ask why the loop is built the way it is.

**Include (lessons first, each with its evidence):**

1. *Specification gaming and the guard* (two-tank: constant flagging, breaking one scenario to win on
   average → asymmetric false-positive cost and the regression guard).
2. *Check the test bed before the search* (quadruple tank: faults never applied, decision grid,
   wrong loop pairing; the oracle exposed the plateau). Keep Table `tab:four`.
3. *Reasoning is needed, low effort is enough for detection* (Figure `fig:reasoning`, Table
   `tab:reasoning`). Keep; it is the only model ablation in the thesis. Note it was run once per
   setting.
4. *The search needs a loose guard early, failure traces, one change at a time and a measured record*
   (coordination runs, `results/coordination/README.md`). These four are exactly what the mill trainer
   inherited. Replace the 11-row run table with one sentence per change; the full table to the
   appendix.
5. *A comparator is only as good as its tuning, and generated code can encode the loops it was
   trained with* (champion 265.4 vs tuned MPC 158.8, 67 % worse; it was within 1.3 % of the untuned
   MPC with the old loops; the champion lost 59 points when the PI loops were retuned). Keep
   `tab:coord-main`; drop or shorten `tab:coord-metrics` and `tab:coord-kind`.
6. *Ranking under nominal conditions does not predict robustness* (stress tests: the tuned MPC +156 %
   at 3 mm noise, the champion +3 %). Keep `tab:coord-stress` in compact form. This is the same
   finding as on the mill under measurement noise, which is why it earns its place.

**Remove or move:**
- Single and two-tank sections: one paragraph each (setup in two sentences, the finding). Details to
  the appendix.
- The fault-detection interface and score: appendix.
- *Changes to the training loop* and *Runs*: fold into lesson 4.
- *The generated supervisor* (coordination champion description): keep a short version; it shows the
  LLM building a steady-state optimiser with an estimator and a trim, an MPC-like structure. Drop the
  numbered five-step walkthrough unless pages allow.
- *Status of the confirmatory comparison* and the four-tank protocol: one paragraph. It was registered
  (version 2) and never run, because the mill and its real comparator became available and the
  budget went there. Its design was reused for the mill protocol. The detailed text goes to the
  appendix.
- The open TODOs in these chapters (repeat reasoning settings, trace the beyond-range pump
  scenarios, confirm which constants cause the loss) can be dropped: they are not worth the time
  now. Say "not investigated further" where it matters.

### 5 The grinding circuit and the comparison (new; created on this branch from `method.tex` `sec:mill`)

**For:** everything the reader needs to judge the mill comparison as fair: plant, loops, interface,
scenarios, scores, the TD-MPC and how it is run.

**Include:**
- *Simulator and regulatory layer* (draft text is good): Weir's dynsim, reverse ball-mill circuit,
  euler 10 s scan, Weir's five NEXTPlant loops unchanged (`cyclone_valve` off, redundant per Weir);
  2 h episodes from a warm start. A flowsheet figure (new; none exists).
- *Operating point* (`docs/remeasure_mpc_interface.md`): the shipped recipe is not an operating
  point (sump drifts, override limit cycle; `docs/phase0_findings.md`), the nominal 9 cyclones / 11 psi /
  1.697 t/m³ / 50 t/h / 13 rpm gives level 75 %, P80 188 µm. Worth a sentence: Phase 0 found this, and
  it affects every controller.
- *Interface*: the TD-MPC's five setpoints and limits, its 30 sensors, window, wrapper limits. Decision
  interval now **300 s** for the main comparison (Kaige, 2026-11-03: a recommended operator cadence),
  60 s and 900 s as variants. The draft still says 60 s; update.
- *Scenarios and batteries:* disturbance kinds (feed flow, ore density, solids, combined at 0.75x),
  patterns (step, ramp, sine; nominal target steps), dev range = the TD-MPC's training coverage,
  **2 per cell: 28 dev / 28 validation / 24 beyond** (draft says 14/14/12; update). Beyond values
  explicitly, as Kaige asked (memory of the 2026-11-05 meeting; `llm_supervisor/scenarios.py`):
  1.25-2x the dev half-widths, e.g. feed 1050-1150 or 1375-1450 m³/h. Sealed battery: five parts.
  A table of all ranges.
- *Score* (draft Eq. `eq:mill-score` is outdated): the multi-objective score in
  `configs/supervisor.yaml` `score_weights`: P80 outside 180-200 µm (5 per µm·h), level band 70-80 %
  and CL band 400-600 % (0.1 per s), safety (1 per s), energy per tonne of ore (10 per kWh/t), CL
  away from 500 % (0.02 per %·h), exceptions (1000); P80 IAE and setpoint travel reported, not scored.
  Explain the two decisions behind it: travel weight removed (`docs/travel_weight_analysis.md`: it
  dominated 80-90 % of the score and drove deadband tuning), energy added
  (`docs/energy_sweep.md`: mill speed is the energy lever, 12 rpm saves ~6 % kWh/t at nominal feed).
  Then the **control penalty** (score minus energy) and the **normalised score** (1 = best,
  `docs/normalised_score.md`; otto decided 2026-11-06: reported beside, training unchanged).
- *The TD-MPC* (draft paragraph *Evaluation of the TD-MPC* is good): `autumn-night-41`, deployed
  model, trained on constant feed per episode, own reward (product of bells around P80 target, level
  75 %, CL 500 %, plus power term, minus penalties), 300 s action hold, own planner config, reset per
  episode, run in the same harness and wrapper. Training cost/data of the TD-MPC if Kaige can give it
  (for the cost comparison in the discussion).
- *Baselines:* fixed recipe; decentralised PI (density from P80 error, pressure from level).
- *Noise models* (new): `llm_supervisor/noise.py` and `docs/noise/noise_v1.md`, `docs/feed_noise.md`:
  P80 white σ 5 µm; P80 analyser (coloured, held 120 s); `plant` (all sensors: flows ~1 %, densities
  0.01, level 0.5 %, pressure 0.15 psi, plus analyser P80); `feed15` (real feed fluctuations, 15 % of
  flow peak-to-peak over 2 h). Paired draws across controllers; `--noise-seed-offset` for fresh
  draws. A table. Say which sizes are guesses.

**Learned:** the fairness questions (interval, metric, training distribution) took as long to settle
as the training itself, and each changed the ranking. That goes to the discussion; here just state
the choices and who agreed them.

### 6 Results on the grinding circuit (new; skeleton on this branch)

Every table: mean score / reward (and normalised where available), terminal episodes in brackets,
dev / validation / beyond. Use "validation" consistently for the mill (the tank chapters use
"held-out"; say once that the roles differ).

**6.1 Training runs: what the search found and what it cost.**
- Runs: `pilot1` and `effort_medium_run1` (old score, 1 per cell), `v3_low_run1`, `v4_low_run1-3`
  (60 s, `docs/repeated_runs_v4.md`: dev 66.6 ± 1.0 after 6 gens), `pilot_300s` (12 gens, $3.85,
  `docs/pilot_300s/`), `protocol_run1-2` (v5, 300 s: dev 70.0 / 76.2), `explore_run1-3` (v6, $3.23-3.62,
  `docs/explore_exploit.md`), `noise_run1-2` (v7, $3.68 / $3.81, `docs/noise_training.md`).
- Figure: champion score per generation for each 300 s run (data in each run's `final_report.md` /
  `summary.csv`; a plotting script for the mill is still to be written).
- What the LLM found: the levers (mill speed to 12 rpm for energy, pressure for level, density for
  P80), the trial outcomes (pilot: 9 promoted, 15 rollbacks of 36), lines kept per candidate (median
  98 %: runs polish their first design).
- Spread (C3 preview): v5 runs 67.0-76.2 dev with reward 0.76-0.92 from the early mill-speed choice;
  v6 dev spread 1.7. The regression guard can block progress from a bad start (vm-week §8).

**6.2 Main comparison at 300 s (RQ1, exploratory).** Table from `docs/tdmpc/fair_v1_pilot_300s_gen12.md`,
`docs/explore_runs/fair_v1_explore_runs.md`, `docs/normalised_score.md`:

| Controller | Dev | Validation | Beyond |
|---|---|---|---|
| pilot_300s (v5, 12 gens) | 67.0 / 0.922 | 66.8 / 0.920 | 194.1 / 0.725 |
| explore_run1 (v6) | 69.5 / 0.899 | 68.2 / 0.894 | 153.0 / 0.760 |
| explore_run2 (v6) | 67.8 / 0.931 | 67.0 / 0.924 | 151.0 / 0.770 |
| explore_run3 (v6) | 67.9 / 0.876 | 76.3 / 0.854 | 232.4 / 0.701 |
| protocol_run1 (v5) | 70.0 / 0.761 | 78.0 / 0.764 | 238.2 / 0.605 |
| TD-MPC | 72.5 / 0.887 | 111.6 / 0.856 | 662.7 / 0.656 (3) |
| Decentralised PI | 474.4 / 0.513 | 189.9 / 0.583 | 1851.2 / 0.281 |
| Fixed recipe | 2754.7 / 0.188 (18) | 2712.2 / 0.187 (16) | 4310.4 / 0.118 (21) |

Plus: control penalty (pilot 3.3 / 2.8 / 130.0) and kWh/t; per score term; steady/step vs ramp/sine
(the TD-MPC's gap is mostly in ramps and sines, outside its constant-feed training); per-scenario
paired differences (a figure: dot per scenario). Message: the LLM champions match or beat the TD-MPC
on dev, and beat it clearly on validation, on both measures, except explore_run3 and the v5 protocol
runs on reward.

**6.3 Beyond the development range (RQ2, exploratory).** Beyond battery numbers above, terminal
episodes, what fails (mostly sump-level band violations; P80 next), per kind and pattern. A
degradation figure (score or reward vs amplitude level) needs the sealed battery's amplitude parts;
until then show dev vs beyond. Failure modes catalogue (C2): name each with one example trajectory.

**6.4 Score and reward disagree on the sump level.** `docs/explore_runs/reward_terms_v1.md`: the
score charges nothing inside 70-80 %; the reward's level term costs ~8 % at 1 % off 75 % and ~26 % at
2 %. Champions with the same score differ in reward by how tightly they hold 75 %. Level is the
largest reward loss for every controller beyond range. A figure: reward split by term per controller.
This is a result, not a footnote: it shows that the comparison depends on the objective, and it
explains every case where an LLM champion wins on score but loses on reward.

**6.5 Decision interval.** `docs/tdmpc/fair_v1.md`, `fair_v1_900.md`, `fair_v1_pilot_300s_gen12.md`:
every controller is tuned to its rate. v4 champions (trained at 60 s) beat the TD-MPC at 60 s, lose at
300 s; the 300 s pilot beats it at 300 s and 900 s (441.9 vs 1119.6 dev) and no longer breaks at 60 s
(89.0). The TD-MPC at 900 s falls to near PI level. One table, intervals as rows.

**6.6 Robustness to noise.** The strongest section after the main comparison. From
`docs/noise/noise_v1.md`, `docs/feed_noise.md`, `docs/noise_training.md` (branch `feed-noise`), vm-week
§3, §5-7:
- P80 measurement noise: the TD-MPC does not read P80 (not in its inputs), so it is unaffected;
  the champions barely move (pilot under analyser noise 71.1 / 74.7 / 185.8).
- Plant-wide measurement noise **reverses the noise-free ranking**: explore_run2 (best without
  noise, reward 0.931) becomes the worst champion (0.529); explore_run3 (weakest) the most robust
  (0.782). The cause is one line: a level trend from two samples 60 s apart. Replacing that line with a
  5-minute least-squares slope lifts its noisy reward to 0.706 and lowers the clean one to 0.834.
- Training under measurement noise (v7) makes champions insensitive to it, but not clearly better than
  the most robust noise-free champion.
- Feed fluctuations (`feed15`) hurt everyone, the TD-MPC most (beyond: 3 → 7 → 11 terminal episodes
  for none / feed / feed + measurement); every champion keeps a higher reward than the TD-MPC under
  every noise. Dev reward table (vm-week §6) as the section's main table.
- Measurement method: one noise draw per scenario is not enough (one scenario's score doubled
  between draws); noise-trained runs are tested on fresh draws.
- Fairness caveat: the TD-MPC was trained without noise too, and Weir's feed generator could randomise
  its training feed.

**6.7 The generated supervisors.** What a champion looks like: length (pilot_300s: 125 lines), the
structure (level-trend estimator driving the pressure setpoint, ore-density feedforward, P80 trim of
the density setpoint, cyclone count, mill speed fixed at 11.8 rpm for energy), rule count (the goal document lists "rule count" as a complexity measure; not measured yet:
count branches/thresholds per champion, cheap to script), and how readable it is. Be honest: the
mill champions use terse names and few comments compared with the coordination champion. The
explore_run2 noise diagnosis (6.6) is the best evidence that the code can be inspected and fixed.

**6.8 Confirmatory results (sealed test).** H0,1, H0,2, C3 with intervals, after the protocol runs.
Placeholder until then. If not run: this section becomes a list of what the exploratory results can
and cannot claim (champions were selected on dev/validation; three runs per setting; no significance
test; validation is in the promotion rule; TD-MPC trained on constant feed for another reward).

**What we learned (for the chapter's summary):** an LLM-written, ~100-line deterministic supervisor
can match or beat the deployed TD-MPC on this simulator at its own decision interval, degrades more
gracefully beyond range and under noise (fewer terminal episodes), but the result depends on the run
(spread), the metric (score vs reward on the level) and the conditions (noise reverses rankings).

### 7 Discussion

**Keep from the draft:** *The evaluation matters as much as the model* (extend with mill examples:
decision interval, metric, energy dominating the score, normalisation); *Reasoning* (shorten);
*Interpretability* (rewrite with mill examples); *Limitations* (rewrite).

**Replace:** *Coordination against MPC* → one paragraph inside a new *Fairness of the comparison*.

**New sections:**
- *Fairness of the comparison:* same simulator, interface, wrapper, scenarios and two metrics; but the
  TD-MPC was trained on constant feed, without noise, for its own reward, by someone else, while the
  LLM saw the dev battery. What each asymmetry does to the result, and which way.
- *Variance and lock-in:* runs polish their first design; explore/exploit narrows the spread; the
  guard blocks from a bad start; several runs are needed (C3).
- *Robustness and where it comes from:* graceful failure (zero terminal episodes) rather than better
  average performance per scenario; the estimator line; noise-free selection does not select for
  robustness; the four-tank stress test showed the same with an MPC.
- *Interpretability in practice:* the one-line diagnosis; constants that tie code to loop tuning
  (four-tank); terse code from the mill runs; what an engineer would need (comments, names, rule count).
- *Cost and practicality:* ~$3-4 and ~2.5 h on one VM per run; compare with the TD-MPC's training if
  known; operators' 5-minute cadence; retraining when loops change.
- *Generality:* the method was kept free of mill-specific choices (standing rule); what would change
  for another plant (lineage priorities could come from the score's terms).

### 8 Conclusions and future work

**For:** answer RQ1, RQ2 and C3 directly, one paragraph each, then the main lessons about the method.

**Future work candidates:** train the TD-MPC with feed randomisation and noise for a symmetric noise
comparison; feed-fluctuation training for the LLM; a level objective both metrics agree on; several
operating points; model comparison on the mill (Sonnet/Haiku, DeepSeek, effort levels); plant data /
deployment in advisory mode; automatic retraining when loops change; rule-count and readability
study with operators.

### Appendices

- A: a mill champion, full listing with a few margin comments (pilot_300s or explore_run2; the
  latter pairs with the noise diagnosis). Keep the 43-line quadruple-tank listing only if pages allow.
- B: tank test-bed details (fault-detection interface and score, single/two-tank scenarios, full
  coordination run table).
- C: the four-tank protocol (version 2) as registered.
- D: an excerpt of the prompt (structure, with the cached and changing parts marked), since the goal
  document promises that prompts are documented.
- E: noise model parameters.

---

## 5. Figures and tables to make

| Figure / table | Data | Script |
|---|---|---|
| Three-layer architecture | exists | `figures/three_layer_architecture.drawio` |
| Mill flowsheet with the five setpoints and loops | Weir's YAML | new (drawio) |
| Champion score per generation, 300 s runs | `runs/training/*/` on the VM; `final_report.md` | new (mill repo) |
| Main comparison per-scenario paired differences | `docs/tdmpc/*.csv`, `docs/explore_runs/*.csv` | new |
| Reward split by term | `docs/explore_runs/reward_terms_v1.csv` | `scripts/reward_terms.py` output; plot new |
| Trajectories: one dev, one beyond, champion vs TD-MPC (level, P80, setpoints) | rerun one episode each | new (no API calls) |
| Decision-interval table | `docs/tdmpc/fair_v1*.md` | exists as tables |
| Noise axis: reward per controller x condition | `docs/feed_noise.md`, `docs/noise/*.csv` | new |
| Degradation vs amplitude (H0,2) | sealed battery | after the protocol |
| Quadruple-tank reasoning figure | exists | `make_thesis_figures.py` |

---

## 6. Consistency checklist for the rewrite

- Decision interval: 300 s is the main comparison everywhere (the draft says 60 s in several places).
- Batteries: 28 / 28 / 24 for training, 216 sealed. Not 14 / 14 / 12.
- Score: the multi-objective score; Eq. `eq:mill-score` in the draft is the old one.
- "Validation" (mill) vs "held-out" (tanks): explain once, then use consistently.
- The fair_v1 table in the draft (`tab:mill-tdmpc`) is the 60 s exploratory comparison: keep it as
  a variant in 6.5, not as the main result.
- Models: DeepSeek on the tanks, Claude Opus 5.5 effort low on the mill.
- Every number should come from a merged doc; `feed-noise` is not merged yet.

---

## 7. What changed in the LaTeX on this branch

- New `chapters/mill_setup.tex` (*The grinding circuit and the comparison*): the old `sec:mill` text
  from `method.tex`, unchanged apart from section headings, with TODOs listing the updates in
  Section 4 above.
- New `chapters/mill_results.tex` (*Results on the grinding circuit*): section skeleton 6.1-6.8 with
  TODOs pointing here, and the old first-comparison paragraph and `tab:mill-tdmpc` moved in as the
  60 s variant.
- `method.tex`: the four-tank protocol replaced by a short mill-protocol section with TODOs; the
  four-tank protocol text moved to the end of `coordination.tex` (`sec:coord-protocol`).
- `main.tex`: chapter order Introduction, Background, Method, Toy, Coordination, Grinding circuit,
  Results, Discussion, Conclusions. The two tank chapters are not merged yet: that needs rewriting,
  which is otto's call (Section 4, Ch. 4 above).
- Not compiled here (no TeX in the cloud container); compile locally with the commands in `CLAUDE.md`.

### 2026-11-25: mill-first skeleton (otto: move away from the tanks)

otto chose the guide's alternative in Section 2: no tank chapter. Structure now:

| # | Chapter | File |
|---|---|---|
| 1 | Introduction | `introduction.tex` |
| 2 | Background (grinding-circuit control, TD-MPC, program search, gaming, paired statistics; fault detection removed) | `background.tex` |
| 3 | Method, the synthesis framework, ending with a one-page *Lessons from developing the method on tank processes* (`sec:dev-lessons`) and the registered mill protocol | `method.tex` |
| 4 | The grinding circuit and the comparison: plant, operating point, interface (300 s), batteries and ranges, score equation, control penalty, normalised score, TD-MPC, baselines, noise categories | `mill_setup.tex` |
| 5 | Results on the grinding circuit: runs, main comparison at 300 s, by objective, beyond range, score vs reward, decision interval, noise, the supervisors, sealed test (TODO) | `mill_results.tex` |
| 6 | Discussion (mill themes) | `discussion.tex` |
| 7 | Conclusions and future work | `conclusions.tex` |
| A | Mill champion listing (TODO) | `appendix_mill_champion.tex` |
| B | Development on tank processes: all tank lessons with evidence, test-bed details, run table, four-tank protocol | `appendix_tanks.tex` |
| C, D | Prompt excerpt, noise parameters (TODO) | `appendix_prompt.tex`, `appendix_noise.tex` |

Chapters 4 and 5 carry the merged numbers from the mill repo's `docs/` (PROTOCOL.md v1, tdmpc/,
explore_runs/, normalised_score.md, noise/, feed_noise.md, noise_training.md) in tables, with short
factual text; the interpretation and the sealed test are `\TODO`s. Compiles cleanly (55 pages).
