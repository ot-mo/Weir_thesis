# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-05T10:34:57+00:00

## Current champion vs baselines

Source hash: `878139a7f5b5`

| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |
|---|---|---|---|---|
| Development (drives promotion) | 533.4 | 533.4 | 203.7 | 192.9 |
| Held-out development | 478.7 | 478.7 | 193.8 | 191.1 |
| Beyond development range (never shown to the LLM) | 1583.0 | 1583.0 | 1123.6 | 1110.9 |

## Trial history

- Total candidates logged: 9
  - REJECTED_REGRESSION: 6
  - ROLLBACK: 2
  - REJECTED_SECURITY: 1

## Token usage per API request, by model and reasoning effort

| Model | Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning | Est. cost total |
|---|---|---|---|---|---|---|---|
| deepseek-flash | low | 9 | 8623 | 5675 | 57982 | 54735 | $0.32 |

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|

## Lessons learned so far

(none recorded yet)
