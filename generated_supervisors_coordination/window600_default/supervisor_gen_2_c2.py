def supervise(telemetry_window, active_setpoints, objectives):
    A1 = 0.0035
    A2 = 0.003
    A3 = 0.002
    A4 = 0.0025
    g = 9.81
    C = math.sqrt(2.0 * g)
    nom_k1 = 0.00085
    nom_k2 = 0.00095
    nom_gamma1 = 0.20
    nom_gamma2 = 0.20
    nom_g1 = nom_gamma1 * nom_k1
    nom_c3 = (1.0 - nom_gamma2) * nom_k2
    nom_c4 = (1.0 - nom_gamma1) * nom_k1
    nom_g2 = nom_gamma2 * nom_k2

    target = float(objectives['production_target'])
    h2_band = objectives['h2_band']
    upper_lim = float(objectives['upper_level_limit'])
    sp_lim = objectives['setpoint_limits']
    lo_sp = float(sp_lim[0])
    hi_sp = float(sp_lim[1])

    N = len(telemetry_window)
    if N < 2:
        h1 = max(lo_sp, min(hi_sp, active_setpoints['h1']))
        h2 = max(lo_sp, min(hi_sp, active_setpoints['h2']))
        return {'diagnosis': 'fallback: window too small', 'adjusted_setpoints': {'h1': h1, 'h2': h2}}

    lambda_ = 0.98
    w = 1.0
    sum_w = 0.0
    sum_w_v1 = 0.0
    sum_w_z1 = 0.0
    sum_w_v1z1 = 0.0
    sum_w_v1sq = 0.0
    sum_w_v2 = 0.0
    sum_w_z2 = 0.0
    sum_w_v2z2 = 0.0
    sum_w_v2sq = 0.0
    sum_w_x2_c3 = 0.0
    sum_w_xy_c3 = 0.0
    sum_w_x2_c4 = 0.0
    sum_w_xy_c4 = 0.0

    for i in range(N-1, 0, -1):
        row = telemetry_window[i]
        row_prev = telemetry_window[i-1]
        h1_i = row['h1']; h1_prev = row_prev['h1']
        h2_i = row['h2']; h2_prev = row_prev['h2']
        h3_i = row['h3']; h3_prev = row_prev['h3']
        h4_i = row['h4']; h4_prev = row_prev['h4']
        v1_i = row['v1']
        v2_i = row['v2']
        dh1 = h1_i - h1_prev
        dh2 = h2_i - h2_prev
        dh3 = h3_i - h3_prev
        dh4 = h4_i - h4_prev
        sqrt_h1 = math.sqrt(max(0.0, h1_i))
        sqrt_h2 = math.sqrt(max(0.0, h2_i))
        sqrt_h3 = math.sqrt(max(0.0, h3_i))
        sqrt_h4 = math.sqrt(max(0.0, h4_i))
        z1 = dh1 + A1 * C * sqrt_h1 - A3 * C * sqrt_h3
        z2 = dh2 + A2 * C * sqrt_h2 - A4 * C * sqrt_h4
        z3 = dh3 + A3 * C * sqrt_h3
        z4 = dh4 + A4 * C * sqrt_h4
        sum_w += w
        sum_w_v1 += w * v1_i
        sum_w_z1 += w * z1
        sum_w_v1z1 += w * v1_i * z1
        sum_w_v1sq += w * v1_i * v1_i
        sum_w_v2 += w * v2_i
        sum_w_z2 += w * z2
        sum_w_v2z2 += w * v2_i * z2
        sum_w_v2sq += w * v2_i * v2_i
        sum_w_x2_c3 += w * v2_i * v2_i
        sum_w_xy_c3 += w * z3 * v2_i
        sum_w_x2_c4 += w * v1_i * v1_i
        sum_w_xy_c4 += w * z4 * v1_i
        w *= lambda_

    if sum_w < 1e-12:
        c3 = nom_c3; c4 = nom_c4; g1 = nom_g1; d1 = 0.0; g2 = nom_g2; d2 = 0.0
    else:
        mean_v1 = sum_w_v1 / sum_w
        mean_z1 = sum_w_z1 / sum_w
        var_v1 = sum_w_v1sq / sum_w - mean_v1 * mean_v1
        if var_v1 > 1e-8:
            cov_v1z1 = sum_w_v1z1 / sum_w - mean_v1 * mean_z1
            g1 = cov_v1z1 / var_v1
        else:
            g1 = nom_g1
        d1 = mean_z1 - g1 * mean_v1

        mean_v2 = sum_w_v2 / sum_w
        mean_z2 = sum_w_z2 / sum_w
        var_v2 = sum_w_v2sq / sum_w - mean_v2 * mean_v2
        if var_v2 > 1e-8:
            cov_v2z2 = sum_w_v2z2 / sum_w - mean_v2 * mean_z2
            g2 = cov_v2z2 / var_v2
        else:
            g2 = nom_g2
        d2 = mean_z2 - g2 * mean_v2

        if sum_w_x2_c3 > 1e-8:
            c3 = sum_w_xy_c3 / sum_w_x2_c3
        else:
            c3 = nom_c3
        if sum_w_x2_c4 > 1e-8:
            c4 = sum_w_xy_c4 / sum_w_x2_c4
        else:
            c4 = nom_c4

    def clamp(x, lo, hi):
        if x < lo: return lo
        if x > hi: return hi
        return x

    c3 = clamp(c3, 0.0001, 0.002)
    c4 = clamp(c4, 0.0001, 0.002)
    g1 = clamp(g1, 0.00005, 0.001)
    g2 = clamp(g2, 0.00005, 0.001)
    d1 = clamp(d1, -0.01, 0.01)
    d2 = clamp(d2, -0.01, 0.01)

    active_h1 = float(active_setpoints['h1'])
    active_h2 = float(active_setpoints['h2'])
    h2_low = float(h2_band[0])
    h2_high = float(h2_band[1])

    K1 = 1000.0 * A1 * C
    K2 = 1000.0 * A2 * C

    Q2_min_safety = K2 * math.sqrt(0.02)
    Q2_max_safety = K2 * math.sqrt(1.5)
    if target > Q2_min_safety:
        h1_max_safety = ((target - Q2_min_safety) / K1) ** 2
    else:
        h1_max_safety = 0.0
    if target > Q2_max_safety:
        h1_min_safety = ((target - Q2_max_safety) / K1) ** 2
    else:
        h1_min_safety = 0.0
    h1_max_Q = (target / K1) ** 2 if target > 0 else 0.0
    h1_hi = min(1.5, h1_max_safety, h1_max_Q, hi_sp)
    h1_lo = max(0.02, h1_min_safety, lo_sp)
    if h1_lo >= h1_hi:
        h1_ret = max(lo_sp, min(hi_sp, active_h1))
        h2_ret = max(lo_sp, min(hi_sp, active_h2))
        return {'diagnosis': 'fallback: no feasible h1 range', 'adjusted_setpoints': {'h1': h1_ret, 'h2': h2_ret}}

    best_cost = 1e300
    best_h1 = active_h1
    best_h2 = active_h2
    steps = 200
    for i in range(steps + 1):
        h1 = h1_lo + (h1_hi - h1_lo) * i / steps
        Q1 = K1 * math.sqrt(h1)
        Q2 = target - Q1
        if Q2 <= 0.0:
            continue
        h2 = (Q2 / K2) ** 2
        if h2 < 0.02 or h2 > 1.5:
            continue
        rhs1 = Q1 / 1000.0 - d1
        rhs2 = Q2 / 1000.0 - d2
        det = g1 * g2 - c3 * c4
        if abs(det) < 1e-14:
            continue
        u1 = (rhs1 * g2 - c3 * rhs2) / det
        u2 = (g1 * rhs2 - c4 * rhs1) / det
        if c3 > 1e-12:
            h3_pred = (c3 * u2 / A3) ** 2 / (2.0 * g)
        else:
            h3_pred = 0.0
        if c4 > 1e-12:
            h4_pred = (c4 * u1 / A4) ** 2 / (2.0 * g)
        else:
            h4_pred = 0.0
        cost = 100.0 * (abs(h1 - active_h1) + abs(h2 - active_h2))
        if h2 < h2_low:
            cost += 5000.0 * (h2_low - h2)
        if h2 > h2_high:
            cost += 5000.0 * (h2_high - h2)
        if h3_pred > upper_lim:
            cost += 5000.0 * (h3_pred - upper_lim)
        if h4_pred > upper_lim:
            cost += 5000.0 * (h4_pred - upper_lim)
        cost += 500.0 * max(0.0, h3_pred - 0.72)
        cost += 500.0 * max(0.0, h4_pred - 0.72)
        cost += 10000.0 * (max(0.0, 1.0 - u1) + max(0.0, u1 - 12.0) + max(0.0, 1.0 - u2) + max(0.0, u2 - 12.0))
        cost += 200.0 * (max(0.0, u1 - 11.0) + max(0.0, u2 - 11.0))
        if h1 < 0.02:
            cost += 1e6 * (0.02 - h1)
        if h1 > 1.5:
            cost += 1e6 * (h1 - 1.5)
        if h2 < 0.02:
            cost += 1e6 * (0.02 - h2)
        if h2 > 1.5:
            cost += 1e6 * (h2 - 1.5)
        if cost < best_cost:
            best_cost = cost
            best_h1 = h1
            best_h2 = h2

    h1_ret = max(lo_sp, min(hi_sp, best_h1))
    h2_ret = max(lo_sp, min(hi_sp, best_h2))

    diag = 'model-based: c3=%.5f c4=%.5f g1=%.5f d1=%.5f g2=%.5f d2=%.5f' % (c3, c4, g1, d1, g2, d2)
    return {
        'diagnosis': diag,
        'adjusted_setpoints': {'h1': h1_ret, 'h2': h2_ret},
    }
