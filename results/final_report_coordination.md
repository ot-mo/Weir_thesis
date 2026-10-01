# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-01T12:35:35+00:00

## Current champion vs baselines

Source hash: `d957c6c4e3dd`

| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |
|---|---|---|---|---|
| Development (drives promotion) | 199.4 | 518.2 | 144.1 | 138.8 |
| Held-out development | 252.7 | 434.3 | 214.3 | 195.3 |
| Beyond development range (never shown to the LLM) | 1282.6 | 1507.6 | 1163.2 | 1207.7 |

## Trial history

- Total candidates logged: 8
  - REJECTED_REGRESSION: 3
  - PROMOTED: 2
  - ROLLBACK: 2
  - REJECTED_SECURITY: 1

## Token usage per API request, by reasoning effort

| Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning |
|---|---|---|---|---|---|
| low | 11 | 8153 | 5585 | 45782 | 43820 |

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|
| gen_1 | 3 | 234.70 | 272.12 |
| gen_2 | 1 | 199.36 | 252.65 |

## Lessons learned so far

- A draw-off from tank1 raises tank3 because the h1 loop pushes pump2 harder; lowering h1's setpoint and raising h2's keeps tank3 below its limit with production on target.
- Extra outflow from tank2 needs the opposite split: raise the h1 setpoint and lower h2 so pump1 works less and tank4 stays low.
- When pump2 gain oscillates, measured h3 excess should directly lower the h1 setpoint to reduce v2, even if production target is unchanged.
- Slope-based disturbance estimates can mask true imbalance during transients, so direct limit-violation feedback must override them to avoid sustained upper-level violations.
