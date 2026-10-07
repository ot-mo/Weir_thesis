# Coordination protocol analysis (DRY RUN on validation batteries - not results)

Policies: window50_run1, window50_run2, window50_run3 (n = 3); comparator: `mpc_tuned`; bootstrap B = 10000, seed 7.

## H0,1 / RQ1 (development range)

- LLM mean 281.2, tuned MPC mean 157.2, difference +124.0 (95 % CI +60.8 to +216.8; 90 % CI +67.6 to +198.9).
- H0,1 rejected: True. Equivalent within +-15.7 (10 % of MPC): False.

## H0,2 / RQ2 (degradation with amplitude)

| Level | dev | x2 |
|---|---|---|
| LLM mean log(1+score) | 5.188 | 6.854 |
| MPC mean log(1+score) | 4.511 | 6.110 |

- Slope difference (LLM - MPC) +0.067 per unit amplitude (95 % CI -0.255 to +0.330); H0,2 rejected: False.

## C3 (variance between independently generated policies)

- Per-policy mean (development range): {'window50_run1': 243.23, 'window50_run2': 242.22, 'window50_run3': 358.17}
- Median 243.2, IQR 242.7-300.7, range 242.2-358.2, SD 66.7 (95 % CI 34.7-418.9, chi-square; bootstrap 0.0-66.9).
- Promotions per run: {'window50_run1': 1, 'window50_run2': 2, 'window50_run3': 1}; runs without a promotion: 0.

## Secondary: per-metric differences (development range, Holm-adjusted)

| Metric | LLM | MPC | p | p (Holm) |
|---|---|---|---|---|
| production_iae_l | 198.16 | 116.88 | 0.000 | 0.000 |
| band_violation_s | 6.83 | 0.00 | 0.030 | 0.150 |
| upper_violation_s | 28.59 | 0.00 | 0.040 | 0.160 |
| safety_violation_s | 0.00 | 0.00 | 1.000 | 1.000 |
| setpoint_tv_m | 0.12 | 0.40 | 0.000 | 0.000 |
| saturation_s | 44.05 | 69.50 | 0.399 | 1.000 |
| recovery_s | 303.50 | 169.30 | 0.000 | 0.000 |
| wrapper_interventions | 0.00 | 0.00 | 1.000 | 1.000 |
