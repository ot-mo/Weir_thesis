# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-01T12:53:54+00:00

## Current champion vs baselines

Source hash: `878139a7f5b5`

| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |
|---|---|---|---|---|
| Development (drives promotion) | 518.2 | 518.2 | 144.1 | 138.8 |
| Held-out development | 434.3 | 434.3 | 214.3 | 195.3 |
| Beyond development range (never shown to the LLM) | 1507.6 | 1507.6 | 1163.2 | 1207.7 |

## Trial history

- Total candidates logged: 8
  - REJECTED_REGRESSION: 7
  - ROLLBACK: 1

## Token usage per API request, by reasoning effort

| Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning |
|---|---|---|---|---|---|
| low | 8 | 7400 | 4416 | 52381 | 49457 |

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|

## Lessons learned so far

- When a disturbance drives tank-3 level toward its limit, lowering the h1 setpoint and raising h2 shifts flow demand to pump 1 and restores h3 margin.
- Pump-gain loss or saturation is relieved by lowering that pump's own lower-tank setpoint, trimming required voltage while the paired setpoint keeps production constant.
- Upper levels depend on pump volumetric flow, not voltage, so a pump-gain loss saturates the pump without first moving tank-3 or tank-4 levels.
- Estimating tank-3 and tank-4 drain flows from measured upper levels lets the supervisor predict setpoint effects without knowing the pump gains.
