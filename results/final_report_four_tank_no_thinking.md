# Four-Tank MIMO Supervisor Training Report

Generated: 2026-09-30T14:11:42+00:00

## Current champion

- Source hash: `59698c64c162`
- Dev battery score: 11836.62
- Held-out validation battery score: 11353.06
- Dev/validation gap: -483.56 (consistent with dev performance)

## Trial history

- Total candidates logged: 24
  - ROLLBACK: 13
  - NOT_SELECTED: 5
  - PROMOTED: 3
  - REJECTED_REGRESSION: 2
  - REJECTED_SECURITY: 1

## Token usage per API request, by reasoning effort

| Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning |
|---|---|---|---|---|---|
| none | 24 | 7510 | 3349 | 2049 | 0 |

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Validation score |
|---|---|---|---|
| gen_1 | 2 | 35855.63 | 41059.40 |
| gen_2 | 4 | 23414.05 | 34046.18 |
| gen_3 | 4 | 11836.62 | 11353.06 |

## Known open issues / lessons learned so far

- A lower-tank leak makes the leaking tank's own PI loop saturate at the 12 V pump limit with tracking error far above healthy settled means.
- With off-diagonal pairing, a leak in one lower tank lowers the other loop's effort because the leaked flow partly drains through the shared path.
- Sustained pump effort above 11.5 V reliably indicates a leak in the corresponding lower tank, because the PI loop saturates at the 12 V limit.
- When a lower tank leaks, its own loop effort saturates while the other loop's effort may drop due to shared outflow paths.
- A lower-tank leak is better detected by its own loop's sustained high effort than by error, since setpoint trimming suppresses error.
- With off-diagonal pairing, lowering one leaking tank's setpoint steadies its loop effort, so lingering level deficit plus effort detects the continued leak.
- Trimming a leaking tank's setpoint lowers loop effort, so leak flags must be held until effort and deficit both fall together.
- A cross-coupled off-diagonal pair lets one leak pull the other loop's effort down, so each tank needs its own baseline-relative test.
- The sum of both loop efforts is setpoint-insensitive and exceeds 20 V during a leak, so it detects leaks after setpoint trimming.
- Trimming only the leaking tank's setpoint leaves the combined effort high, allowing an early restore of the healthy tank's setpoint.
