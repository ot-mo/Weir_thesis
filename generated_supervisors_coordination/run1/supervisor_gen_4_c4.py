def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    c = math.sqrt(2.0 * 9.81)
    gamma1 = 0.20
    gamma2 = 0.20
    QNOM = 16.35286638873749
    h1a = 0.30
    h2a = 0.35
    try:
        h1a = float(active_setpoints['h1'])
        h2a = float(active_setpoints['h2'])
    except Exception:
        pass
    fallback = {'diagnosis': 'hold setpoints', 'adjusted_setpoints': {'h1': h1a, 'h2': h2a}}
    try:
        Q_t = float(objectives['production_target'])
        band = objectives['h2_band']
        h2lo = float(band[0])
        h2hi = float(band[1])
        ulim = float(objectives['upper_level_limit'])
        lim = objectives['setpoint_limits']
        splo = float(lim[0])
        sphi = float(lim[1])
    except Exception:
        return fallback

    n = len(telemetry_window)
    if n < 5:
        return fallback

    m = 20
    if n < m:
        m = n
    start = n - m

    u1_list = []
    u2_list = []
    Q1_list = []
    Q2_list = []
    v1_list = []
    v2_list = []
    for i in range(start+1, n):
        try:
            h1 = float(telemetry_window[i]['h1'])
            h2 = float(telemetry_window[i]['h2'])
            h3 = float(telemetry_window[i]['h3'])
            h4 = float(telemetry_window[i]['h4'])
            v1 = float(telemetry_window[i]['v1'])
            v2 = float(telemetry_window[i]['v2'])
            h1p = float(telemetry_window[i-1]['h1'])
            h2p = float(telemetry_window[i-1]['h2'])
            h3p = float(telemetry_window[i-1]['h3'])
            h4p = float(telemetry_window[i-1]['h4'])
        except Exception:
            continue
        dh4 = h4 - h4p
        dh3 = h3 - h3p
        u1 = 1000.0 * (a4 * c * math.sqrt(max(h4, 0.0)) + dh4)
        u2 = 1000.0 * (a3 * c * math.sqrt(max(h3, 0.0)) + dh3)
        Q1 = 1000.0 * a1 * c * math.sqrt(max(h1, 0.0))
        Q2 = 1000.0 * a2 * c * math.sqrt(max(h2, 0.0))
        u1_list.append(u1)
        u2_list.append(u2)
        Q1_list.append(Q1)
        Q2_list.append(Q2)
        v1_list.append(v1)
        v2_list.append(v2)

    if len(u1_list) < 3:
        return fallback

    def linreg(y_list, x_list):
        nn = len(x_list)
        if nn < 3:
            return 0.25, 0.0
        sx = sum(x_list)
        sy = sum(y_list)
        sxx = sum(x*x for x in x_list)
        sxy = sum(x*y for x, y in zip(x_list, y_list))
        den = nn * sxx - sx * sx
        if abs(den) < 1e-9:
            return 0.25, sy / nn
        slope = (nn * sxy - sx * sy) / den
        intercept = (sy - slope * sx) / nn
        if slope < 0.0:
            slope = 0.0
        if slope > 2.0:
            slope = 2.0
        return slope, intercept

    y1 = [Q1_list[i] - u2_list[i] for i in range(len(Q1_list))]
    r1, d1_reg = linreg(y1, u1_list)
    y2 = [Q2_list[i] - u1_list[i] for i in range(len(Q2_list))]
    r2, d2_reg = linreg(y2, u2_list)

    Q1_last = Q1_list[-1]
    Q2_last = Q2_list[-1]
    u1_last = u1_list[-1]
    u2_last = u2_list[-1]
    d1 = Q1_last - u2_last - r1 * u1_last
    d2 = Q2_last - u1_last - r2 * u2_last

    c1_sum = 0.0
    c1_cnt = 0
    c2_sum = 0.0
    c2_cnt = 0
    for i in range(len(u1_list)):
        if v1_list[i] > 2.0:
            c1_sum += u1_list[i] / v1_list[i]
            c1_cnt += 1
        if v2_list[i] > 2.0:
            c2_sum += u2_list[i] / v2_list[i]
            c2_cnt += 1
    c1_eff = c1_sum / c1_cnt if c1_cnt > 0 else 0.8 * k1 * 1000.0
    c2_eff = c2_sum / c2_cnt if c2_cnt > 0 else 0.8 * k2 * 1000.0
    if c1_eff < 0.1:
        c1_eff = 0.8 * k1 * 1000.0
    if c2_eff < 0.1:
        c2_eff = 0.8 * k2 * 1000.0

    Q_actual = float(telemetry_window[n-1]['production'])
    kk = 5 if n >= 5 else n
    Q_vals = []
    for j in range(kk):
        Q_vals.append(float(telemetry_window[n-1-j]['production']))
    if kk >= 2:
        slope_Q = (Q_vals[0] - Q_vals[-1]) / (kk - 1)
    else:
        slope_Q = 0.0
    Q_pred = Q_actual + slope_Q * 5.0
    Q_err = Q_t - Q_pred
    if abs(Q_err) < 0.1:
        Q_err = 0.0
    Q_scan = Q_t + 0.6 * Q_err
    if Q_scan < 0.5 * Q_t:
        Q_scan = 0.5 * Q_t
    if Q_scan > 1.5 * Q_t:
        Q_scan = 1.5 * Q_t

    def evaluate(Q1_cand):
        Q2_cand = Q_scan - Q1_cand
        if Q1_cand < 0.0 or Q2_cand < 0.0:
            return None
        den = 1.0 - r1 * r2
        if abs(den) < 0.1:
            r1n = gamma1 / (1.0 - gamma1)
            r2n = gamma2 / (1.0 - gamma2)
            den = 1.0 - r1n * r2n
            if abs(den) < 1e-6:
                return None
            u1 = (Q2_cand - d2 - r2n * Q1_cand + r2n * d1) / den
            u2 = (Q1_cand - d1 - r1n * Q2_cand + r1n * d2) / den
        else:
            u1 = (Q2_cand - d2 - r2 * Q1_cand + r2 * d1) / den
            u2 = (Q1_cand - d1 - r1 * Q2_cand + r1 * d2) / den
        if u1 < -0.5 or u2 < -0.5:
            return None
        if u1 < 0.0:
            u1 = 0.0
        if u2 < 0.0:
            u2 = 0.0
        v1 = u1 / c1_eff if c1_eff > 1e-6 else 0.0
        v2 = u2 / c2_eff if c2_eff > 1e-6 else 0.0
        h1 = (Q1_cand / (1000.0 * a1 * c)) ** 2
        h2 = (Q2_cand / (1000.0 * a2 * c)) ** 2
        h3 = (u2 / (1000.0 * a3 * c)) ** 2
        h4 = (u1 / (1000.0 * a4 * c)) ** 2
        penalty = 0.0
        if h1 < 0.02:
            penalty += 10000.0 * (0.02 - h1)
        if h1 > 1.5:
            penalty += 10000.0 * (h1 - 1.5)
        if h2 < 0.02:
            penalty += 10000.0 * (0.02 - h2)
        if h2 > 1.5:
            penalty += 10000.0 * (h2 - 1.5)
        if h1 < splo:
            penalty += 1000.0 * (splo - h1)
        if h1 > sphi:
            penalty += 1000.0 * (h1 - sphi)
        if h2 < splo:
            penalty += 1000.0 * (splo - h2)
        if h2 > sphi:
            penalty += 1000.0 * (h2 - sphi)
        if h2 < h2lo:
            penalty += 100.0 * (h2lo - h2)
        if h2 > h2hi:
            penalty += 100.0 * (h2 - h2hi)
        if h3 > ulim:
            penalty += 1000.0 * (h3 - ulim)
        if h4 > ulim:
            penalty += 1000.0 * (h4 - ulim)
        if v1 < 1.0:
            penalty += 1000.0 * (1.0 - v1)
        if v1 > 12.0:
            penalty += 1000.0 * (v1 - 12.0)
        if v2 < 1.0:
            penalty += 1000.0 * (1.0 - v2)
        if v2 > 12.0:
            penalty += 1000.0 * (v2 - 12.0)
        travel = abs(h1 - h1a) + abs(h2 - h2a)
        feasible = (penalty < 1e-6)
        return (feasible, penalty, travel, h1, h2, v1, v2, h3, h4)

    Q1_min = 1000.0 * a1 * c * math.sqrt(max(0.02, splo))
    Q1_max = 1000.0 * a1 * c * math.sqrt(min(1.5, sphi))
    Q2_min = 1000.0 * a2 * c * math.sqrt(max(0.02, splo))
    Q2_max = 1000.0 * a2 * c * math.sqrt(min(1.5, sphi))
    lo = max(Q1_min, Q_scan - Q2_max)
    hi = min(Q1_max, Q_scan - Q2_min)
    if lo > hi:
        Q_scan = Q_t
        lo = max(Q1_min, Q_scan - Q2_max)
        hi = min(Q1_max, Q_scan - Q2_min)
        if lo > hi:
            return fallback

    best_feas = None
    best_feas_travel = 1e12
    best_any = None
    best_any_penalty = 1e12
    N = 60
    for i in range(N + 1):
        Q1_cand = lo + (hi - lo) * i / N
        res = evaluate(Q1_cand)
        if res is None:
            continue
        feasible, penalty, travel, h1, h2, v1, v2, h3, h4 = res
        if feasible:
            if travel < best_feas_travel:
                best_feas_travel = travel
                best_feas = res
        else:
            if penalty < best_any_penalty:
                best_any_penalty = penalty
                best_any = res

    if best_feas is not None:
        h1_b = best_feas[3]
        Q1_b = 1000.0 * a1 * c * math.sqrt(max(h1_b, 0.0))
        step = (hi - lo) / N / 5.0
        for j in range(-5, 6):
            Q1_cand = Q1_b + j * step
            if Q1_cand < lo or Q1_cand > hi:
                continue
            res = evaluate(Q1_cand)
            if res is None:
                continue
            feasible, penalty, travel, h1, h2, v1, v2, h3, h4 = res
            if feasible and travel < best_feas_travel:
                best_feas_travel = travel
                best_feas = res

    if best_feas is not None:
        h1_new = best_feas[3]
        h2_new = best_feas[4]
        diag = 'Q_scan=%.2f Q_err=%.2f travel=%.3f' % (Q_scan, Q_err, best_feas_travel)
    elif best_any is not None:
        h1_new = best_any[3]
        h2_new = best_any[4]
        diag = 'Q_scan=%.2f Q_err=%.2f PEN=%.1f' % (Q_scan, Q_err, best_any_penalty)
    else:
        return fallback

    max_step = 0.03
    dh1 = h1_new - h1a
    dh2 = h2_new - h2a
    if abs(dh1) > max_step:
        dh1 = max_step if dh1 > 0 else -max_step
    if abs(dh2) > max_step:
        dh2 = max_step if dh2 > 0 else -max_step
    h1_out = h1a + dh1
    h2_out = h2a + dh2

    h1_out = max(min(h1_out, min(1.5, sphi)), max(0.02, splo))
    h2_out = max(min(h2_out, min(1.5, sphi)), max(0.02, splo))
    band_lo = max(h2lo, max(0.02, splo))
    band_hi = min(h2hi, min(1.5, sphi))
    if band_lo <= band_hi:
        h2_out = max(min(h2_out, band_hi), band_lo)
    Q2_out = 1000.0 * a2 * c * math.sqrt(max(h2_out, 0.0))
    Q1_out = Q_scan - Q2_out
    if Q1_out < 0.0:
        Q1_out = 0.0
    h1_out = (Q1_out / (1000.0 * a1 * c)) ** 2
    h1_out = max(min(h1_out, min(1.5, sphi)), max(0.02, splo))

    return {'diagnosis': diag, 'adjusted_setpoints': {'h1': h1_out, 'h2': h2_out}}