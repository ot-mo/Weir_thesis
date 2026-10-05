def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1_nom = 0.00085
    k2_nom = 0.00095
    gamma1_nom = 0.20
    gamma2_nom = 0.20
    C1 = gamma1_nom * k1_nom
    C2 = gamma2_nom * k2_nom
    A3_nom = (1 - gamma2_nom) * k2_nom
    A4_nom = (1 - gamma1_nom) * k1_nom

    Q_target = objectives['production_target']
    h2_band = objectives['h2_band']
    upper_limit = objectives['upper_level_limit']
    sp_lo, sp_hi = objectives['setpoint_limits']

    n = len(telemetry_window)
    if n < 2:
        return {'diagnosis': 'insufficient data', 'adjusted_setpoints': active_setpoints}

    last_change = -1
    for i in range(1, n):
        if (telemetry_window[i]['sp_h1'] != telemetry_window[i-1]['sp_h1'] or
            telemetry_window[i]['sp_h2'] != telemetry_window[i-1]['sp_h2']):
            last_change = i
    if last_change > n - 120:
        return {'diagnosis': 'transient from recent setpoint change, holding', 'adjusted_setpoints': active_setpoints}

    num_avg = min(20, n)
    h1_sum = h2_sum = h3_sum = h4_sum = v1_sum = v2_sum = 0.0
    for i in range(n - num_avg, n):
        s = telemetry_window[i]
        h1_sum += s['h1']
        h2_sum += s['h2']
        h3_sum += s['h3']
        h4_sum += s['h4']
        v1_sum += s['v1']
        v2_sum += s['v2']
    h1_cur = h1_sum / num_avg
    h2_cur = h2_sum / num_avg
    h3_cur = h3_sum / num_avg
    h4_cur = h4_sum / num_avg
    v1_cur = v1_sum / num_avg
    v2_cur = v2_sum / num_avg

    if n >= 20:
        idx_old = n - 20
        h1_old = telemetry_window[idx_old]['h1']
        h2_old = telemetry_window[idx_old]['h2']
        dh1_dt = (h1_cur - h1_old) / 20.0
        dh2_dt = (h2_cur - h2_old) / 20.0
    else:
        dh1_dt = 0.0
        dh2_dt = 0.0

    if v2_cur > 0.5:
        A3_est = a3 * math.sqrt(2*g*h3_cur) / v2_cur
    else:
        A3_est = A3_nom
    if v1_cur > 0.5:
        A4_est = a4 * math.sqrt(2*g*h4_cur) / v1_cur
    else:
        A4_est = A4_nom

    d1_est = dh1_dt + a1*math.sqrt(2*g*h1_cur) - A3_est*v2_cur - C1*v1_cur
    d2_est = dh2_dt + a2*math.sqrt(2*g*h2_cur) - A4_est*v1_cur - C2*v2_cur

    def h2_of_h1(h1):
        Q_m3 = Q_target / 1000.0
        term = Q_m3 - a1*math.sqrt(2*g*h1)
        if term <= 0:
            return None
        return (term / a2)**2 / (2*g)

    def predict_v(h1, h2):
        rhs1 = a1*math.sqrt(2*g*h1)
        rhs2 = a2*math.sqrt(2*g*h2)
        b1 = rhs1 - d1_est
        b2 = rhs2 - d2_est
        det = C1*C2 - A3_est*A4_est
        if abs(det) < 1e-12:
            return None, None
        v1 = (b1*C2 - A3_est*b2) / det
        v2 = (C1*b2 - A4_est*b1) / det
        return v1, v2

    def predict_h3_h4(h1, h2):
        v1, v2 = predict_v(h1, h2)
        if v1 is None:
            return None, None
        h3 = (A3_est * v2)**2 / (2*g*a3**2)
        h4 = (A4_est * v1)**2 / (2*g*a4**2)
        return h3, h4

    Q_current_setpoint = 1000.0 * (a1*math.sqrt(2*g*active_setpoints['h1']) + a2*math.sqrt(2*g*active_setpoints['h2']))
    Q_error = abs(Q_current_setpoint - Q_target)

    count_upper = 0
    count_band = 0
    count_sat = 0
    start_idx = max(0, n - 60)
    for i in range(start_idx, n):
        s = telemetry_window[i]
        if s['h3'] > upper_limit - 0.05 or s['h4'] > upper_limit - 0.05:
            count_upper += 1
        if s['h2'] < h2_band[0] + 0.02 or s['h2'] > h2_band[1] - 0.02:
            count_band += 1
        if s['v1'] > 11.5 or s['v2'] > 11.5:
            count_sat += 1

    need_move = False
    reason = 'constraints satisfied'
    if Q_error > 0.1:
        need_move = True
        reason = 'target change'
    elif count_upper >= 10:
        need_move = True
        reason = 'sustained upper level near limit'
    elif count_band >= 10:
        need_move = True
        reason = 'sustained h2 near band'
    elif count_sat >= 10:
        need_move = True
        reason = 'sustained pump saturation'

    if not need_move:
        return {
            'diagnosis': 'constraints satisfied, holding setpoints',
            'adjusted_setpoints': {'h1': active_setpoints['h1'], 'h2': active_setpoints['h2']}
        }

    best_h1 = active_setpoints['h1']
    best_cost = float('inf')
    h1 = sp_lo
    step = 0.005
    while h1 <= sp_hi + 1e-9:
        h2 = h2_of_h1(h1)
        if h2 is not None and sp_lo <= h2 <= sp_hi:
            cost = 0.0
            cost += 100.0 * (abs(h1 - active_setpoints['h1']) + abs(h2 - active_setpoints['h2']))
            if h2 < h2_band[0]:
                cost += 3000.0 * (h2_band[0] - h2)
            if h2 > h2_band[1]:
                cost += 3000.0 * (h2 - h2_band[1])
            h3_pred, h4_pred = predict_h3_h4(h1, h2)
            if h3_pred is not None:
                if h3_pred > upper_limit:
                    cost += 3000.0 * (h3_pred - upper_limit)
                if h3_pred > 0.70:
                    cost += 300.0 * (h3_pred - 0.70)
                if h4_pred > upper_limit:
                    cost += 3000.0 * (h4_pred - upper_limit)
                if h4_pred > 0.70:
                    cost += 300.0 * (h4_pred - 0.70)
                v1, v2 = predict_v(h1, h2)
                if v1 > 12:
                    cost += 5000.0 * (v1 - 12)
                if v1 < 1:
                    cost += 5000.0 * (1 - v1)
                if v2 > 12:
                    cost += 5000.0 * (v2 - 12)
                if v2 < 1:
                    cost += 5000.0 * (1 - v2)
            else:
                cost += 1e6
            if cost < best_cost:
                best_cost = cost
                best_h1 = h1
        h1 += step

    if reason == 'target change':
        max_step = 0.2
    else:
        max_step = 0.03
    delta = best_h1 - active_setpoints['h1']
    if delta > max_step:
        delta = max_step
    elif delta < -max_step:
        delta = -max_step
    new_h1 = active_setpoints['h1'] + delta
    new_h1 = max(sp_lo, min(sp_hi, new_h1))
    new_h2 = h2_of_h1(new_h1)
    if new_h2 is None:
        new_h2 = active_setpoints['h2']
    new_h2 = max(sp_lo, min(sp_hi, new_h2))

    diag = 'optimized: ' + reason + ', h1 ' + str(round(active_setpoints['h1'],3)) + '->' + str(round(new_h1,3)) + ', h2 ' + str(round(active_setpoints['h2'],3)) + '->' + str(round(new_h2,3))
    return {
        'diagnosis': diag,
        'adjusted_setpoints': {'h1': new_h1, 'h2': new_h2}
    }
