# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-05T12:08:26+00:00

## Current champion vs baselines

Source hash: `15bf904ce8a4`

| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |
|---|---|---|---|---|
| Development (drives promotion) | 231.5 | 533.4 | 203.7 | 192.9 |
| Held-out development | 247.5 | 478.7 | 193.8 | 191.1 |
| Beyond development range (never shown to the LLM) | 1339.3 | 1583.0 | 1123.6 | 1110.9 |

## Trial history

- Total candidates logged: 9
  - ROLLBACK: 9

## Token usage per API request, by model and reasoning effort

| Model | Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning | Est. cost total |
|---|---|---|---|---|---|---|---|
| deepseek-flash | low | 9 | 19354 | 3669 | 16154 | 13280 | $0.11 |
- Share of the champion's lines kept by a candidate: median 97% (range 84%-98%, 9 candidates)

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|

## Lessons learned so far

- Low-pass filtering the estimated load over a time constant comparable to the oscillation period cuts setpoint churn while still tracking sustained offsets within the loop settling time.
- Because production depends only on h1 and h2, smoother setpoint commands reduce the PI loops' tracking error and hence production deviation during oscillatory disturbances.
- Including measured level slopes in the mass-balance residual removes the ninety-degree phase lag that makes a supervisor shift setpoints out of phase with an oscillatory feed disturbance.
- A steady-state residual underestimates the peak of an oscillatory feed disturbance, so upper-level safety margins must be based on the slope-corrected estimate.
- Filtering the inferred feed offset with a 150 s time constant suppresses zero-mean oscillatory setpoint churn but adds lag on sustained step offsets.
- A filtered supervisor still leaves residual out-of-phase setpoint travel when the disturbance period is only about twice the filter time constant.
