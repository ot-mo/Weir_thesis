# Four-Tank Setpoint-Coordination Supervisor Training Report

Generated: 2026-10-05T20:32:21+00:00

## Current champion vs baselines

Source hash: `94c1e9b2765e`

| Battery | LLM champion | Fixed recipe | MPC (estimated) | MPC (oracle) |
|---|---|---|---|---|
| Development (drives promotion) | 206.3 | 533.4 | 203.7 | 192.9 |
| Held-out development | 214.9 | 478.7 | 193.8 | 191.1 |
| Beyond development range (never shown to the LLM) | 1199.2 | 1583.0 | 1123.6 | 1110.9 |

## Trial history

- Total candidates logged: 12
  - ROLLBACK: 6
  - PROMOTED: 4
  - NOT_SELECTED: 2

## Token usage per API request, by model and reasoning effort

| Model | Effort | Requests | Avg prompt | Avg cache hit | Avg completion | Avg reasoning | Est. cost total |
|---|---|---|---|---|---|---|---|
| deepseek-flash | high | 12 | 20730 | 2688 | 83606 | 79762 | $0.63 |
- Share of the champion's lines kept by a candidate: median 95% (range 83%-99%, 12 candidates)

## Score trajectory (promoted candidates only)

| Generation | Candidate | Dev score | Held-out score |
|---|---|---|---|
| gen_1 | 2 | 230.33 | 226.20 |
| gen_2 | 3 | 227.43 | 229.17 |
| gen_3 | 1 | 212.36 | 221.01 |
| gen_4 | 1 | 206.27 | 214.91 |

## Lessons learned so far

- During oscillations the upper tanks store flow, so dividing their outflow by the split misreads that storage as a pump-gain loss.
- A pump-gain estimate biased low makes the optimizer shift production away from that pump, loading the other pump and raising its upper tank level.
- A load estimate built from the upper-tank outflows lags a swinging disturbance by the upper tank's storage time constant, so the split compensation arrives a half-cycle late.
- An upward split trim needs 4/3 of its flow from pump 2 and lifts tank 3 by about 155 m per m3/s, so it must be bounded by tank-3 headroom.
- The measured production error is in phase with the flow disturbance, but a setpoint change needs 1.5-2 minutes to reach the product, so a proportional error trim corrects each swing after its trough.
- Extrapolating the production error one plant lag ahead with its own 90 s slope, but forcing the prediction never to change the sign of the measured error, anticipates a swing without harming step responses.
- A fixed post-setpoint-change hold of 45 s staircases the supervisor's update rate at ~50 s, so during a several-minute oscillation the split compensation lags the load by about a half cycle.
- Shortening that hold lets the split track a swinging disturbance more finely, whereas lengthening it (100 s) was measured to worsen production for every disturbance type.
