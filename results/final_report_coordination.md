# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-01T12:13:19+00:00

## Current champion vs baselines

Source hash: `ec9612b9bf4c`

| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |
|---|---|---|---|---|
| Development (drives promotion) | 234.7 | 518.2 | 144.1 | 138.8 |
| Held-out development | 272.1 | 434.3 | 214.3 | 195.3 |
| Beyond development range (never shown to the LLM) | 1399.1 | 1507.6 | 1163.2 | 1207.7 |

## Trial history

- Total candidates logged: 4
  - REJECTED_REGRESSION: 2
  - REJECTED_SECURITY: 1
  - PROMOTED: 1

## Token usage per API request, by reasoning effort

| Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning |
|---|---|---|---|---|---|
| low | 7 | 6809 | 2853 | 52456 | 51037 |

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|
| gen_1 | 3 | 234.70 | 272.12 |

## Lessons learned so far

- A draw-off from tank1 raises tank3 because the h1 loop pushes pump2 harder; lowering h1's setpoint and raising h2's keeps tank3 below its limit with production on target.
- Extra outflow from tank2 needs the opposite split: raise the h1 setpoint and lower h2 so pump1 works less and tank4 stays low.
