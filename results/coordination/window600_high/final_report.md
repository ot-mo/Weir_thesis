# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-05T13:11:26+00:00

## Current champion vs baselines

Source hash: `675c7ff04a75`

| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |
|---|---|---|---|---|
| Development (drives promotion) | 227.4 | 533.4 | 203.7 | 192.9 |
| Held-out development | 229.2 | 478.7 | 193.8 | 191.1 |
| Beyond development range (never shown to the LLM) | 1181.4 | 1583.0 | 1123.6 | 1110.9 |

## Trial history

- Total candidates logged: 6
  - ROLLBACK: 3
  - PROMOTED: 2
  - NOT_SELECTED: 1

## Token usage per API request, by model and reasoning effort

| Model | Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning | Est. cost total |
|---|---|---|---|---|---|---|---|
| deepseek-flash | high | 6 | 18990 | 1536 | 80193 | 76798 | $0.30 |
- Share of the champion's lines kept by a candidate: median 98% (range 83%-99%, 6 candidates)

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|
| gen_1 | 2 | 230.33 | 226.20 |
| gen_2 | 3 | 227.43 | 229.17 |

## Lessons learned so far

- During oscillations the upper tanks store flow, so dividing their outflow by the split misreads that storage as a pump-gain loss.
- A pump-gain estimate biased low makes the optimizer shift production away from that pump, loading the other pump and raising its upper tank level.
- A load estimate built from the upper-tank outflows lags a swinging disturbance by the upper tank's storage time constant, so the split compensation arrives a half-cycle late.
- An upward split trim needs 4/3 of its flow from pump 2 and lifts tank 3 by about 155 m per m3/s, so it must be bounded by tank-3 headroom.
