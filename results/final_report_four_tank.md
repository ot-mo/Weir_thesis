# Four-Tank MIMO Supervisor Training Report

Generated: 2026-09-30T13:53:55+00:00

## Current champion

- Source hash: `a4c2148dee3e`
- Dev battery score: 2626.82
- Held-out validation battery score: 2599.60
- Dev/validation gap: -27.22 (consistent with dev performance)

## Trial history

- Total candidates logged: 12
  - NOT_SELECTED: 5
  - PROMOTED: 3
  - ROLLBACK: 2
  - REJECTED_REGRESSION: 1
  - SKIPPED: 1

## Token usage per API request, by reasoning effort

| Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning |
|---|---|---|---|---|---|
| low | 4 | 6284 | 0 | 27832 | 25930 |

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Validation score |
|---|---|---|---|
| gen_1 | 4 | 6127.21 | 7100.14 |
| gen_2 | 3 | 4626.98 | 3599.67 |
| gen_3 | 2 | 2626.82 | 2599.60 |

## Known open issues / lessons learned so far

- A within-window recent-vs-past ratio of loop effort cannot detect a fault that outlives half the window (~25 s): both halves then lie inside the fault and the leaking loop is pinned at the 12 V pump rail, so the ratio collapses to ~1.0 and the fault is booked as missed for its entire duration.
- In this quadruple-tank unit an outlet leak is compensated by the leaking tank's OWN off-diagonal loop saturating at the pump limit (tank1 leak -> pump2 = 12 V; tank2 leak -> pump1 = 12 V) while the level sits 0.2-0.25 m below its setpoint; with only h1/h2 measured, the leak must be inferred from that tank's own loop, and the partner loop carries no reliable signature (it can even move the opposite way via the 20% / 80% split coupling).
- The post-fault recovery of a wound-up loop reproduces the fault signature (effort 11.8-12.0 V with |error| up to 0.18 for 10-30 s after the leak has physically stopped), so any effort/error-based detector must also require that the level is no longer refilling, or it books false positives exactly when the fault clears.
- The two diag loops are cross-coupled through the split shares (pump 1 sends 20% of its flow straight into tank 1, pump 2 sends 20% into tank 2), so when one tank's leak clears and the partner pump comes off its 12 V rail back toward its ~9 V operating point, the HEALTHY tank's own loop must pick up the missing inflow: v_own moves by gamma*k_partner*dv_partner/k_own ~ 0.5-1.0 V plus the loop's natural +-1 V settling oscillation. Any absolute rail detector must therefore keep >= ~0.6 V of head-room above the healthy effort envelope (10.59 V for the tank1 loop) or the partner's recovery is booked as a false positive on a tank that never faulted.
- Detecting on the MEAN of the loop effort over the whole 10 s telemetry window throws away a full call of onset latency: a fault starting 3-5 s before a call pulls the ramp down with pre-fault samples (tank1 severe: true mean 10.8 V at t=410 while the last samples are already 11.5-12.0 V), so the flag slips to t=420 and 10 seconds (10 missed-anomaly events) are lost for free. Counting rail samples inside the window recovers that call with no loss of robustness because the fault-free envelope never comes near the rail.
- A leak can be accompanied by a RISING level: if the fault begins while the tank is still far below its new leak-limited equilibrium (e.g. during the start-up transient, or after the supervisor has lowered the setpoint), the settled level creeps back up at up to ~1.3 mm/s toward that lower equilibrium. A 'level is rising => not a fault' gate that only compares 10 s mean drift against a few mm therefore systematically misses early-onset leaks; the discriminator has to be the magnitude of the level RATE, which separates leakage creep (<=0.0013 m/s) from post-clear refilling (0.0025-0.0043 m/s) by a factor of about 3-6.
- Gating the detector on |error| is self-defeating because the supervisor's own mitigation shrinks it: lowering a leaking tank's setpoint by the allowed 0.04 m while the loop is saturated leaves the level unchanged, so the loop error drops from ~0.09 m (nominal setpoint, 1.5x leak) to ~0.05 m, right into the band produced by spurious cross-coupling sags (~0.03-0.04 m). The effort rail is the only mitigation-invariant signature of a leak here.
- A leak's onset is marked by a falling level while loop error exceeds the healthy settled maximum, which precedes pump saturation by several seconds.
- Because start-up has large errors but rising levels, requiring large error plus falling level detects leaks early without start-up false positives.
