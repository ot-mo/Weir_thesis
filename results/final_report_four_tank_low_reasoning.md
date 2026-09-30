# Four-Tank MIMO Supervisor Training Report

Generated: 2026-09-30T14:25:01+00:00

## Current champion

- Source hash: `73a00b4e7e42`
- Dev battery score: 2635.26
- Held-out validation battery score: 2608.69
- Dev/validation gap: -26.57 (consistent with dev performance)

## Trial history

- Total candidates logged: 12
  - ROLLBACK: 7
  - NOT_SELECTED: 3
  - PROMOTED: 2

## Token usage per API request, by reasoning effort

| Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning |
|---|---|---|---|---|---|
| low | 12 | 6076 | 1963 | 22635 | 21363 |

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Validation score |
|---|---|---|---|
| gen_1 | 2 | 4385.26 | 3608.69 |
| gen_2 | 1 | 2635.26 | 2608.69 |

## Known open issues / lessons learned so far

- A tank's own off-diagonal loop saturates at 12 V when that tank leaks, while the other loop's effort falls, so saturation flags faults without cross-coupling false positives.
- Measured level slope, not effort alone, separates a cleared leak's fast recovery from a sustained leak's flat equilibrium.
- Leak onset drops the tank level sharply before its loop effort rises, so a 15 mm/10 s level-drop test flags faults earlier than effort thresholds.
- After a leak clears the loop effort stays high while level rises, so requiring non-positive slope prevents recovery false positives.
- A leak in one lower tank raises the other lower tank's level through non-minimum-phase cross-coupling, making its nominal-target error negative and suppressing false anomaly flags there.
- Using nominal-target error for detection prevents our own setpoint adjustments from being misread as leaks, because level tracks the adjusted setpoint while nominal error persists.
