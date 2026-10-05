# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-05T12:39:10+00:00

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
| deepseek-flash | low | 10 | 19657 | 5440 | 30812 | 27986 | $0.21 |
- Share of the champion's lines kept by a candidate: median 98% (range 94%-99%, 9 candidates)

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|

## Lessons learned so far

(none recorded yet)
