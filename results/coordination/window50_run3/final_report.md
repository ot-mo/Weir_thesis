# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-01T13:14:56+00:00

## Current champion vs baselines

Source hash: `412b4d556c5a`

| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |
|---|---|---|---|---|
| Development (drives promotion) | 192.6 | 518.2 | 144.1 | 138.8 |
| Held-out development | 283.9 | 434.3 | 214.3 | 195.3 |
| Beyond development range (never shown to the LLM) | 1381.0 | 1507.6 | 1163.2 | 1207.7 |

## Trial history

- Total candidates logged: 16
  - ROLLBACK: 10
  - REJECTED_REGRESSION: 4
  - NOT_SELECTED: 1
  - PROMOTED: 1

## Token usage per API request, by reasoning effort

| Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning |
|---|---|---|---|---|---|
| low | 16 | 11976 | 7200 | 40227 | 36589 |

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|
| gen_1 | 1 | 192.62 | 283.94 |

## Lessons learned so far

- A window-integrated lower-tank mass balance recovers the exact lumped feed or pump-gain disturbance at steady state, letting a stateless supervisor predict the pump voltages it will need.
- Because the two lower-tank outflows sum to production, shifting share from the tank whose upper level nears its limit to its partner restores feasibility without changing Q.
- Adding a temporary production-target bias proportional to measured Q error drives setpoints to overdrive pumps, cutting transient production loss without steady-state offset.
- Setting upper-level constraint margins larger than observed closed-loop overshoot prevents h3/h4 violations when PI loops lag oscillating disturbances.
- Directly reacting to a measured upper level above a warning threshold via the production split prevents limit violations that steady-state feasibility checks miss during transients.
- A small production-error bias on the effective target reduces integral Q error during target changes but must be filtered to avoid amplifying oscillating disturbances.
- Instantaneous mass-balance residuals from the last few samples capture oscillating feed disturbances that a 50-second window average cancels, enabling timely setpoint shifts.
- Using measured upper-level rates to dynamically tighten the upper-level constraint margin prevents limit violations during fast oscillations without sacrificing production during quiet periods.
