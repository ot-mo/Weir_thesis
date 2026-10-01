# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-01T12:54:37+00:00

## Current champion vs baselines

Source hash: `878139a7f5b5`

| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |
|---|---|---|---|---|
| Development (drives promotion) | 518.2 | 518.2 | 144.1 | 138.8 |
| Held-out development | 434.3 | 434.3 | 214.3 | 195.3 |
| Beyond development range (never shown to the LLM) | 1507.6 | 1507.6 | 1163.2 | 1207.7 |

## Trial history

- Total candidates logged: 8
  - REJECTED_REGRESSION: 8

## Token usage per API request, by reasoning effort

| Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning |
|---|---|---|---|---|---|
| low | 8 | 7406 | 4416 | 56001 | 53160 |

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|

## Lessons learned so far

- Tank1 receives most of its inflow through upper tank3 from pump 2, so any tank1 deficit raises v2 and pushes h3 toward its limit.
- Shifting the production split toward tank2 lowers pump-2/tank3 duty but raises h2, so the split saturates exactly where h2 leaves its band.
- A draw-off from tank1 raises pump-2 voltage until h3 saturates; lowering the h1 setpoint trades production to tank2 and restores h3 margin.
- Estimating disturbances from lower-tank outflow minus upper-tank inflow lets the supervisor predict upper-level response to setpoint shifts online.
