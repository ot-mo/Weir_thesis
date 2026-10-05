# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-05T11:58:43+00:00

## Current champion vs baselines

Source hash: `15bf904ce8a4`

| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |
|---|---|---|---|---|
| Development (drives promotion) | 231.5 | 533.4 | 203.7 | 192.9 |
| Held-out development | 247.5 | 478.7 | 193.8 | 191.1 |
| Beyond development range (never shown to the LLM) | 1339.3 | 1583.0 | 1123.6 | 1110.9 |

## Trial history

- Total candidates logged: 21
  - ROLLBACK: 18
  - REJECTED_REGRESSION: 2
  - PROMOTED: 1

## Token usage per API request, by model and reasoning effort

| Model | Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning | Est. cost total |
|---|---|---|---|---|---|---|---|
| deepseek-flash | low | 21 | 18206 | 3419 | 38278 | 34965 | $0.53 |
- Share of the champion's lines kept by a candidate: median 97% (range 84%-98%, 9 candidates)

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|
| gen_1 | 1 | 231.50 | 247.46 |

## Lessons learned so far

- Extra inflow into tank2 forces the h2 setpoint up and h1 down, because lowering tank1's share would drive pump2 harder and push h3 over its limit.
- Feed offsets estimated from level slopes (mass balance) stay valid during setpoint transients, whereas steady-state residuals under-estimate them and cause setpoint overshoot.
- A zero-mean oscillatory feed disturbance cancels over a long window, so setpoints should respond only to sustained offsets, never to the instantaneous residual.
- Using the window minimum of the tank1 feed residual pre-biases the split toward tank2, preventing tank3 overflow from periodic or step draw-off.
- Effective pump gain is recovered exactly from an upper tank's mass balance, (dh/dt + outflow)/(split*v), which separates pump-gain loss from feed disturbance.
- Because the production target fixes the sum of the two lower-tank outflows, jumping the setpoints instantly costs no extra travel and removes ramping error.
- Low-pass filtering the estimated load over a time constant comparable to the oscillation period cuts setpoint churn while still tracking sustained offsets within the loop settling time.
- Because production depends only on h1 and h2, smoother setpoint commands reduce the PI loops' tracking error and hence production deviation during oscillatory disturbances.
- Including measured level slopes in the mass-balance residual removes the ninety-degree phase lag that makes a supervisor shift setpoints out of phase with an oscillatory feed disturbance.
- A steady-state residual underestimates the peak of an oscillatory feed disturbance, so upper-level safety margins must be based on the slope-corrected estimate.
- Filtering the inferred feed offset with a 150 s time constant suppresses zero-mean oscillatory setpoint churn but adds lag on sustained step offsets.
- A filtered supervisor still leaves residual out-of-phase setpoint travel when the disturbance period is only about twice the filter time constant.
