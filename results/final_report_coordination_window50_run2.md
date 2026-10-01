# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-01T13:15:49+00:00

## Current champion vs baselines

Source hash: `3f160f87479d`

| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |
|---|---|---|---|---|
| Development (drives promotion) | 175.3 | 518.2 | 144.1 | 138.8 |
| Held-out development | 260.8 | 434.3 | 214.3 | 195.3 |
| Beyond development range (never shown to the LLM) | 1279.0 | 1507.6 | 1163.2 | 1207.7 |

## Trial history

- Total candidates logged: 16
  - REJECTED_REGRESSION: 8
  - ROLLBACK: 5
  - PROMOTED: 2
  - NOT_SELECTED: 1

## Token usage per API request, by reasoning effort

| Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning |
|---|---|---|---|---|---|
| low | 16 | 12504 | 8264 | 34931 | 31881 |

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|
| gen_1 | 1 | 196.01 | 321.79 |
| gen_4 | 4 | 175.32 | 260.79 |

## Lessons learned so far

- A feed draw-off from tank1 raises h3 because the h1 loop increases v2, and shifting production to tank2 (lower h1 setpoint) reduces v2 and h3.
- A pump gain loss or split shift raises the pump voltage needed for a given upper-tank flow; estimating effective path gain from measured v and upper flow predicts saturation.
- During fast pump-gain oscillations, including tank level derivatives in disturbance estimation prevents underestimating the setpoint shift needed to keep upper levels below limits.
- A cost term proportional to current upper-level excess times the corresponding pump voltage encourages faster production shifting and reduces transient limit violations.
- Bias the target total outflow by measured production error so setpoints move before slow PI loops fully correct Q, cutting off-target integral.
- Predict upper-level future as current level plus horizon times measured slope plus effective gain times pump change, letting supervisor lower the pump feeding a rising tank.
- Moving the production split toward tank1 lowers h4 and raises h3 because the two upper tanks are fed by opposite pumps, so upper-level margins trade off.
- Regulating the split on the predicted upper level rather than only its steady value is needed when pump gain oscillates near the level-loop bandwidth.
