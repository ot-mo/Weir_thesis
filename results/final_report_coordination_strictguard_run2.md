# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-01T12:55:23+00:00

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
| low | 8 | 7392 | 4416 | 61232 | 58034 |

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|

## Lessons learned so far

- Tank 3 level is set solely by pump 2 voltage, so the only lever that lowers a near-limit h3 is shifting production demand onto tank 2.
- A pump gain loss appears in the tank mass-balance residual as extra draw-off, so re-estimating effective gains from upper-tank balances keeps voltage predictions honest.
- A tank-1 draw-off raises pump 2 voltage and h3; moving production to tank 2 lowers h3 and relieves pump 2.
- Effective pump gain estimated as upper-tank outflow divided by voltage captures both gain loss and split shifts for prediction.
