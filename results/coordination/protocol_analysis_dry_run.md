# Coordination protocol analysis (DRY RUN on validation batteries - not results)

Policies: window50_run1, window50_run2, window50_run3 (n = 3); comparator: `mpc_tuned`; bootstrap B = 10000, seed 7.

## H0,1 / RQ1 (development range)

- LLM mean 326.3, tuned MPC mean 170.4, difference +155.8 (95 % CI +93.3 to +254.5; 90 % CI +100.4 to +233.8).
- H0,1 rejected: True. Equivalent within +-17.0 (10 % of MPC): False.

## H0,2 / RQ2 (degradation with amplitude)

| Level | dev | x2 |
|---|---|---|
| LLM mean log(1+score) | 5.483 | 6.898 |
| MPC mean log(1+score) | 4.626 | 6.201 |

- Slope difference (LLM - MPC) -0.160 per unit amplitude (95 % CI -0.500 to +0.164); H0,2 rejected: False.

## C3 (variance between independently generated policies)

- Per-policy mean (development range): {'window50_run1': 290.54, 'window50_run2': 291.55, 'window50_run3': 396.76}
- Median 291.6, IQR 291.0-344.2, range 290.5-396.8, SD 61.0 (95 % CI 31.8-383.6, chi-square; bootstrap 0.0-61.3).
- Promotions per run: {'window50_run1': 1, 'window50_run2': 2, 'window50_run3': 1}; runs without a promotion: 0.

## Secondary: per-metric differences (development range, Holm-adjusted)

| Metric | LLM | MPC | p | p (Holm) |
|---|---|---|---|---|
| production_iae_l | 263.57 | 138.62 | 0.000 | 0.000 |
| band_violation_s | 3.29 | 0.00 | 0.054 | 0.216 |
| upper_violation_s | 24.18 | 0.00 | 0.068 | 0.216 |
| safety_violation_s | 0.00 | 0.00 | 1.000 | 1.000 |
| setpoint_tv_m | 0.08 | 0.32 | 0.000 | 0.000 |
| saturation_s | 20.06 | 74.00 | 0.005 | 0.025 |
| recovery_s | 376.87 | 176.23 | 0.000 | 0.000 |
| wrapper_interventions | 0.00 | 0.00 | 1.000 | 1.000 |
