# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-01T13:17:50+00:00

## Current champion vs baselines

Source hash: `8018f0c5208a`

| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |
|---|---|---|---|---|
| Development (drives promotion) | 189.8 | 518.2 | 144.1 | 138.8 |
| Held-out development | 233.8 | 434.3 | 214.3 | 195.3 |
| Beyond development range (never shown to the LLM) | 1102.6 | 1507.6 | 1163.2 | 1207.7 |

## Trial history

- Total candidates logged: 16
  - ROLLBACK: 8
  - REJECTED_REGRESSION: 7
  - PROMOTED: 1

## Token usage per API request, by reasoning effort

| Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning |
|---|---|---|---|---|---|
| low | 16 | 12230 | 7328 | 53941 | 50444 |

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|
| gen_1 | 1 | 189.76 | 233.80 |

## Lessons learned so far

- Shifting production from tank1 to tank2 lowers pump2 voltage and the h3 level but raises pump1 voltage and the h4 level, and vice versa.
- The upper-tank inflow equals a*c*sqrt(h)+dh/dt, so its steady level is predictable from current level and slope without knowing the disturbance.
- Because steady production depends only on the two level setpoints, holding the target-derived pair keeps Q on target under any feed or pump-gain disturbance until a pump saturates.
- A persistent setpoint offset costs no steady production but injects level-tracking transients, so moving the split chatters production whenever the trigger is a transient rather than a projected limit.
- Window-averaged effective gains a=(1-gamma2)k2 and c=(1-gamma1)k1 from measured h3/v2 and h4/v1 predict upper-level response to split changes without knowing the disturbance.
- A one-dimensional scan over h1 along the Q-target curve finds the minimal-travel setpoint pair that satisfies predicted upper-level and pump constraints, avoiding unnecessary setpoint chattering.
- Staying on the constant-Q curve while shifting the production split keeps Q on target even when a pump saturates or an upper level nears its limit.
- Instantaneous feed and effective pump-gain disturbances estimated from lower and upper tank mass balances let a constrained scan predict steady upper levels and pump voltages for any setpoint pair.
