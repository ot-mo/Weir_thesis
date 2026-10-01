def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    gamma1 = 0.20
    gamma2 = 0.20
    c1 = gamma1 * k1
    c2 = gamma2 * k2
    b1_nom = (1.0 - gamma1) * k1
    b2_nom = (1.0 - gamma2) * k2
    NOM_Q = 16.35286638873749
    NOM_H1 = 0.30
    NOM_H2 = 0.35
    target = objectives['production_target']
    h2_lo, h2_hi = objectives['h2_band']
    upper_limit = objectives['upper_level_limit']
    sp_lo, sp_hi = objectives['setpoint_limits']

    sum_b1 = 0.0
    cnt_b1 = 0
    sum_b2 = 0.0
    cnt_b2 = 0
    for s in telemetry_window:
        v1 = s['v1']
        v2 = s['v2']
        if v1 > 1.0:
            sum_b1 += a4 * math.sqrt(2.0 * g * max(0.0, s['h4'])) / v1
            cnt_b1 += 1
        if v2 > 1.0:
            sum_b2 += a3 * math.sqrt(2.0 * g * max(0.0, s['h3'])) / v2
            cnt_b2 += 1
    b1_est = sum_b1 / cnt_b1 if cnt_b1 > 0 else b1_nom
    b2_est = sum_b2 / cnt_b2 if cnt_b2 > 0 else b2_nom
    if b1_est < 0.3 * b1_nom:
        b1_est = 0.3 * b1_nom
    if b1_est > 2.0 * b1_nom:
        b1_est = 2.0 * b1_nom
    if b2_est < 0.3 * b2_nom:
        b2_est = 0.3 * b2_nom
    if b2_est > 2.0 * b2_nom:
        b2_est = 2.0 * b2_nom

    last = telemetry_window[-1]
    h1_m = last['h1']
    h2_m = last['h2']
    h3_m = last['h3']
    h4_m = last['h4']
    v1_m = last['v1']
    v2_m = last['v2']
    L1_meas = a1 * math.sqrt(2.0 * g * max(0.0, h1_m)) - a3 * math.sqrt(2.0 * g * max(0.0, h3_m))
    L2_meas = a2 * math.sqrt(2.0 * g * max(0.0, h2_m)) - a4 * math.sqrt(2.0 * g * max(0.0, h4_m))
    d1_est = L1_meas - c1 * v1_m
    d2_est = L2_meas - c2 * v2_m

    def q_from_h(h, area):
        return 1000.0 * area * math.sqrt(2.0 * g * max(0.0, h))

    def h2_from_h1(h1):
        q1v = q_from_h(h1, a1)
        q2v = target - q1v
        if q2v <= 0.0:
            return None
        return ((q2v / 1000.0) / a2) ** 2 / (2.0 * g)

    def predict(h1, h2):
        A1 = a1 * math.sqrt(2.0 * g * max(0.0, h1))
        A2 = a2 * math.sqrt(2.0 * g * max(0.0, h2))
        denom = b2_est - c1 * c2 / b1_est
        if abs(denom) < 1e-12:
            v2p = (A1 - d1_est) / b2_est
        else:
            v2p = (A1 - d1_est - (c1 / b1_est) * (A2 - d2_est)) / denom
        v1p = (A2 - d2_est - c2 * v2p) / b1_est
        if v2p < 0.0:
            v2p = 0.0
        if v1p < 0.0:
            v1p = 0.0
        h3p = (b2_est * v2p / a3) ** 2 / (2.0 * g)
        h4p = (b1_est * v1p / a4) ** 2 / (2.0 * g)
        return v1p, v2p, h3p, h4p

    scale = (target / NOM_Q) ** 2
    base_h1 = min(sp_hi, max(sp_lo, NOM_H1 * scale))
    base_h2 = min(sp_hi, max(sp_lo, NOM_H2 * scale))

    active_h1 = active_setpoints['h1']
    active_h2 = active_setpoints['h2']
    active_q = q_from_h(active_h1, a1) + q_from_h(active_h2, a2)
    on_target = abs(active_q - target) <= 0.1
    if on_target:
        start_h1, start_h2 = active_h1, active_h2
    else:
        start_h1, start_h2 = base_h1, base_h2

    v1_s, v2_s, h3_s, h4_s = predict(start_h1, start_h2)
    threat = (h3_s > upper_limit - 0.02 or h4_s > upper_limit - 0.02 or
              v1_s > 11.5 or v2_s > 11.5 or
              start_h2 < h2_lo or start_h2 > h2_hi)
    if not threat:
        out_h1 = min(sp_hi, max(sp_lo, start_h1))
        out_h2 = min(sp_hi, max(sp_lo, start_h2))
        return {
            'diagnosis': 'no threat; keeping on-target setpoints',
            'adjusted_setpoints': {'h1': out_h1, 'h2': out_h2},
        }

    best = None
    best_cost = 1e18
    passes = [
        (max(0.02, h2_lo - 0.02), min(1.5, h2_hi + 0.02)),
        (max(0.02, h2_lo - 0.10), min(1.5, h2_hi + 0.10)),
        (0.02, 1.5)
    ]
    for pass_idx, (alo, ahi) in enumerate(passes):
        h = 0.02
        while h <= 1.5 + 1e-9:
            if h < sp_lo or h > sp_hi or h < 0.02 or h > 1.5:
                h += 0.005
                continue
            h2 = h2_from_h1(h)
            if h2 is None:
                h += 0.005
                continue
            if h2 < alo or h2 > ahi:
                h += 0.005
                continue
            if h2 < 0.02 or h2 > 1.5:
                h += 0.005
                continue
            if h2 < sp_lo or h2 > sp_hi:
                h += 0.005
                continue
            v1p, v2p, h3p, h4p = predict(h, h2)
            travel = abs(h - active_h1) + abs(h2 - active_h2)
            cost = 100.0 * travel
            if h2 < h2_lo:
                cost += 4000.0 * (h2_lo - h2)
            if h2 > h2_hi:
                cost += 4000.0 * (h2 - h2_hi)
            if h3p > upper_limit:
                cost += 4000.0 * (h3p - upper_limit)
            if h4p > upper_limit:
                cost += 4000.0 * (h4p - upper_limit)
            if v1p > 12.0:
                cost += 2000.0 * (v1p - 12.0)
            if v2p > 12.0:
                cost += 2000.0 * (v2p - 12.0)
            if v1p < 1.0:
                cost += 500.0 * (1.0 - v1p)
            if v2p < 1.0:
                cost += 500.0 * (1.0 - v2p)
            if cost < best_cost:
                best_cost = cost
                best = (h, h2, h3p, h4p, v1p, v2p)
            h += 0.005
        if best is not None:
            break

    if best is None:
        out_h1, out_h2 = base_h1, base_h2
        diag = 'no feasible candidate; fallback to base'
    else:
        out_h1, out_h2 = best[0], best[1]
        diag = 'threat handled: shifted to h1=%.3f h2=%.3f (pred h3=%.3f h4=%.3f v1=%.1f v2=%.1f)' % (out_h1, out_h2, best[2], best[3], best[4], best[5])
    out_h1 = min(sp_hi, max(sp_lo, out_h1))
    out_h2 = min(sp_hi, max(sp_lo, out_h2))
    return {
        'diagnosis': diag,
        'adjusted_setpoints': {'h1': out_h1, 'h2': out_h2},
    }