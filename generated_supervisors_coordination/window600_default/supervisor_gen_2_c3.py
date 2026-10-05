def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    sqrt2g = (2.0 * g) ** 0.5
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1_nom = 0.00085
    k2_nom = 0.00095
    gamma1_nom = 0.20
    gamma2_nom = 0.20
    g1_nom = gamma1_nom * k1_nom
    g2_nom = gamma2_nom * k2_nom
    c1_nom = (1.0 - gamma1_nom) * k1_nom
    c2_nom = (1.0 - gamma2_nom) * k2_nom
    Q_target = objectives['production_target']
    A_sum = Q_target / 1000.0
    band_lo, band_hi = objectives['h2_band']
    upper_limit = objectives['upper_level_limit']
    sp_lo, sp_hi = objectives['setpoint_limits']
    h_min_safe = 0.02
    h_max_safe = 1.5

    if not telemetry_window:
        return {'diagnosis': 'no telemetry', 'adjusted_setpoints': active_setpoints}
    s = telemetry_window[-1]
    h1 = s['h1']
    h2 = s['h2']
    h3 = s['h3']
    h4 = s['h4']
    v1 = s['v1']
    v2 = s['v2']
    sp1 = s['sp_h1']
    sp2 = s['sp_h2']

    recent_sp_change = False
    target_changed = False
    if len(telemetry_window) >= 130:
        s_past = telemetry_window[-130]
        if abs(s_past['sp_h1'] - sp1) > 1e-6 or abs(s_past['sp_h2'] - sp2) > 1e-6:
            recent_sp_change = True
        if abs(s_past['production_target'] - s['production_target']) > 1e-6:
            target_changed = True

    critical = (h3 > upper_limit + 0.02 or h4 > upper_limit + 0.02 or
                v1 > 11.9 or v2 > 11.9 or
                h2 < band_lo - 0.02 or h2 > band_hi + 0.02 or
                h1 < h_min_safe + 0.01 or h1 > h_max_safe - 0.01 or
                h2 < h_min_safe + 0.01 or h2 > h_max_safe - 0.01)

    if recent_sp_change and not target_changed and not critical:
        return {
            'diagnosis': 'holding setpoints during transient after recent setpoint change',
            'adjusted_setpoints': {'h1': active_setpoints['h1'], 'h2': active_setpoints['h2']}
        }

    A1_meas = a1 * sqrt2g * (h1 ** 0.5) if h1 > 0.0 else 0.0
    A2_meas = a2 * sqrt2g * (h2 ** 0.5) if h2 > 0.0 else 0.0
    if v1 > 1.0 and h4 > 0.01:
        c1_est = a4 * sqrt2g * (h4 ** 0.5) / v1
    else:
        c1_est = c1_nom
    if v2 > 1.0 and h3 > 0.01:
        c2_est = a3 * sqrt2g * (h3 ** 0.5) / v2
    else:
        c2_est = c2_nom
    c1_est = min(0.002, max(0.0001, c1_est))
    c2_est = min(0.002, max(0.0001, c2_est))
    d1_est = A1_meas - (c2_est * v2 + g1_nom * v1)
    d2_est = A2_meas - (c1_est * v1 + g2_nom * v2)
    d1_est = min(0.005, max(-0.005, d1_est))
    d2_est = min(0.005, max(-0.005, d2_est))

    h1_c = active_setpoints['h1']
    h2_c = active_setpoints['h2']

    h1_min = max(h_min_safe, sp_lo)
    if a1 * sqrt2g > 1e-12:
        h1_max_q = (A_sum / (a1 * sqrt2g)) ** 2
    else:
        h1_max_q = h_max_safe
    h1_max = min(h_max_safe, sp_hi, h1_max_q)
    if h1_min > h1_max:
        return {
            'diagnosis': 'no feasible h1 range for target production',
            'adjusted_setpoints': {'h1': h1_c, 'h2': h2_c}
        }

    step = 0.005
    best_h1 = h1_c
    best_h2 = h2_c
    best_cost = None
    h1_val = h1_min
    while h1_val <= h1_max + 1e-9:
        A1_new = a1 * sqrt2g * (h1_val ** 0.5)
        A2_new = A_sum - A1_new
        if A2_new <= 0.0:
            break
        if a2 > 1e-12:
            h2_val = (A2_new / a2) ** 2 / (2.0 * g)
        else:
            h2_val = h2_c
        if h2_val < h_min_safe or h2_val > h_max_safe or h2_val < sp_lo or h2_val > sp_hi:
            h1_val += step
            continue
        det = g1_nom * g2_nom - c2_est * c1_est
        if abs(det) < 1e-12:
            h1_val += step
            continue
        b1 = A1_new - d1_est
        b2 = A2_new - d2_est
        v1_pred = (b1 * g2_nom - c2_est * b2) / det
        v2_pred = (g1_nom * b2 - c1_est * b1) / det
        if v2_pred > 0.0 and a3 > 1e-12:
            h3_pred = (c2_est * v2_pred / a3) ** 2 / (2.0 * g)
        else:
            h3_pred = 0.0
        if v1_pred > 0.0 and a4 > 1e-12:
            h4_pred = (c1_est * v1_pred / a4) ** 2 / (2.0 * g)
        else:
            h4_pred = 0.0
        cost = 100.0 * (abs(h1_val - h1_c) + abs(h2_val - h2_c))
        if h2_val < band_lo:
            cost += 5000.0 * (band_lo - h2_val)
        elif h2_val > band_hi:
            cost += 5000.0 * (h2_val - band_hi)
        soft = 0.05
        if h3_pred > upper_limit - soft:
            cost += 5000.0 * max(0.0, h3_pred - upper_limit) + 500.0 * max(0.0, h3_pred - (upper_limit - soft))
        if h4_pred > upper_limit - soft:
            cost += 5000.0 * max(0.0, h4_pred - upper_limit) + 500.0 * max(0.0, h4_pred - (upper_limit - soft))
        if v1_pred > 11.5:
            cost += 5000.0 * (v1_pred - 11.5)
        elif v1_pred < 1.5:
            cost += 5000.0 * (1.5 - v1_pred)
        if v2_pred > 11.5:
            cost += 5000.0 * (v2_pred - 11.5)
        elif v2_pred < 1.5:
            cost += 5000.0 * (1.5 - v2_pred)
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_h1 = h1_val
            best_h2 = h2_val
        h1_val += step

    if best_cost is None:
        best_h1 = h1_c
        best_h2 = h2_c

    max_step = 0.05
    dh1 = best_h1 - h1_c
    if abs(dh1) > max_step:
        dh1 = max_step if dh1 > 0.0 else -max_step
    h1_cmd = h1_c + dh1
    A1_cmd = a1 * sqrt2g * (h1_cmd ** 0.5) if h1_cmd > 0.0 else 0.0
    A2_cmd = A_sum - A1_cmd
    if A2_cmd <= 0.0:
        h1_cmd = best_h1
        A1_cmd = a1 * sqrt2g * (h1_cmd ** 0.5)
        A2_cmd = A_sum - A1_cmd
    if a2 > 1e-12 and A2_cmd > 0.0:
        h2_cmd = (A2_cmd / a2) ** 2 / (2.0 * g)
    else:
        h2_cmd = h2_c
    h1_cmd = min(sp_hi, max(sp_lo, h1_cmd))
    h1_cmd = min(h_max_safe, max(h_min_safe, h1_cmd))
    h2_cmd = min(sp_hi, max(sp_lo, h2_cmd))
    h2_cmd = min(h_max_safe, max(h_min_safe, h2_cmd))

    diag = 'model-based supervisor: Q_target=%.2f L/s, sp=(%.3f, %.3f)' % (Q_target, h1_cmd, h2_cmd)
    return {
        'diagnosis': diag,
        'adjusted_setpoints': {'h1': h1_cmd, 'h2': h2_cmd}
    }