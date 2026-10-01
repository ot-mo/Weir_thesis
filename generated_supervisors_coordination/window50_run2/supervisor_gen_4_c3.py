def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    gamma1 = 0.20
    gamma2 = 0.20
    K1 = 0.85
    K2 = 0.95
    g = 9.81
    alpha = gamma1 / (1.0 - gamma1)
    beta = gamma2 / (1.0 - gamma2)
    Q_t = objectives['production_target']
    h2_low, h2_high = objectives['h2_band']
    upper_lim = objectives['upper_level_limit']
    sp_lo, sp_hi = objectives['setpoint_limits']
    n = len(telemetry_window)
    if n == 0:
        h1_fb = min(max(active_setpoints['h1'], sp_lo), sp_hi)
        h2_fb = min(max(active_setpoints['h2'], sp_lo), sp_hi)
        return {'diagnosis': 'empty window', 'adjusted_setpoints': {'h1': h1_fb, 'h2': h2_fb}}
    m = min(5, n)
    recent = telemetry_window[-m:]
    avg = {}
    for key in ['h1', 'h2', 'h3', 'h4', 'v1', 'v2', 'production']:
        avg[key] = sum(s[key] for s in recent) / m
    h1c = avg['h1']
    h2c = avg['h2']
    h3c = avg['h3']
    h4c = avg['h4']
    v1c = avg['v1']
    v2c = avg['v2']
    Q_avg = avg['production']
    N = min(20, n)
    def slope(key):
        start = n - N
        xs = []
        ys = []
        for i in range(start, n):
            xs.append(telemetry_window[i]['time'])
            ys.append(telemetry_window[i][key])
        mean_x = sum(xs) / N
        mean_y = sum(ys) / N
        num = 0.0
        den = 0.0
        for i in range(N):
            dx = xs[i] - mean_x
            num += dx * (ys[i] - mean_y)
            den += dx * dx
        if den == 0.0:
            return 0.0
        return num / den
    slope_h1 = slope('h1')
    slope_h2 = slope('h2')
    slope_h3 = slope('h3')
    slope_h4 = slope('h4')
    def q_from_h(h, a):
        if h <= 0.0:
            return 0.0
        return 1000.0 * a * math.sqrt(2.0 * g * h)
    def h_from_q(q, a):
        if q <= 0.0:
            return 0.0
        return (q / (1000.0 * a)) ** 2 / (2.0 * g)
    q1c = q_from_h(h1c, a1)
    q2c = q_from_h(h2c, a2)
    q3c = q_from_h(h3c, a3)
    q4c = q_from_h(h4c, a4)
    if v1c > 0.5:
        G4_est = (q4c + 1000.0 * slope_h4) / v1c
    else:
        G4_est = (1.0 - gamma1) * K1
    if v2c > 0.5:
        G3_est = (q3c + 1000.0 * slope_h3) / v2c
    else:
        G3_est = (1.0 - gamma2) * K2
    G4_est = max(0.05, min(2.0, G4_est))
    G3_est = max(0.05, min(2.0, G3_est))
    A1_est = alpha * G4_est
    A2_est = beta * G3_est
    d1_est = 1000.0 * slope_h1 + q1c - q3c - A1_est * v1c
    d2_est = 1000.0 * slope_h2 + q2c - q4c - A2_est * v2c
    e = Q_t - Q_avg
    Q_des = Q_t + 0.5 * e
    if Q_des < Q_t - 3.0:
        Q_des = Q_t - 3.0
    if Q_des > Q_t + 3.0:
        Q_des = Q_t + 3.0
    if Q_des < 0.1:
        Q_des = 0.1
    def evaluate(h1_sp):
        if h1_sp < 0.02 or h1_sp > 1.5:
            return None
        q1 = q_from_h(h1_sp, a1)
        q2 = Q_des - q1
        if q2 <= 0.001:
            return None
        h2_sp = h_from_q(q2, a2)
        if h2_sp < 0.0:
            return None
        det = A1_est * A2_est - G3_est * G4_est
        if abs(det) < 1e-9:
            return None
        e1 = q1 - d1_est
        e2 = q2 - d2_est
        v1 = (e1 * A2_est - G3_est * e2) / det
        v2 = (A1_est * e2 - e1 * G4_est) / det
        if v1 < -0.01 or v2 < -0.01:
            return None
        q3 = G3_est * v2
        q4 = G4_est * v1
        if q3 < -0.001 or q4 < -0.001:
            return None
        q3 = max(0.0, q3)
        q4 = max(0.0, q4)
        h3_steady = h_from_q(q3, a3)
        h4_steady = h_from_q(q4, a4)
        T = 20.0
        h3_pred = h3c + T * slope_h3 + T * G3_est * (v2 - v2c) / 1000.0
        h4_pred = h4c + T * slope_h4 + T * G4_est * (v1 - v1c) / 1000.0
        h3_risk = max(h3_steady, h3_pred)
        h4_risk = max(h4_steady, h4_pred)
        travel = abs(h1_sp - active_setpoints['h1']) + abs(h2_sp - active_setpoints['h2'])
        viol = 0.0
        if h3_risk > upper_lim:
            viol += 10000.0 * (h3_risk - upper_lim)
        if h4_risk > upper_lim:
            viol += 10000.0 * (h4_risk - upper_lim)
        if h2_sp < h2_low:
            viol += 10000.0 * (h2_low - h2_sp)
        if h2_sp > h2_high:
            viol += 10000.0 * (h2_sp - h2_high)
        if v1 > 12.0:
            viol += 10000.0 * (v1 - 12.0)
        if v2 > 12.0:
            viol += 10000.0 * (v2 - 12.0)
        if v1 < 1.0:
            viol += 10000.0 * (1.0 - v1)
        if v2 < 1.0:
            viol += 10000.0 * (1.0 - v2)
        if h1_sp < 0.02:
            viol += 100000.0 * (0.02 - h1_sp)
        if h1_sp > 1.5:
            viol += 100000.0 * (h1_sp - 1.5)
        if h2_sp < 0.02:
            viol += 100000.0 * (0.02 - h2_sp)
        if h2_sp > 1.5:
            viol += 100000.0 * (h2_sp - 1.5)
        margin = 0.03
        if h3_risk > upper_lim - margin:
            viol += 1000.0 * (h3_risk - (upper_lim - margin))
        if h4_risk > upper_lim - margin:
            viol += 1000.0 * (h4_risk - (upper_lim - margin))
        if v1 > 11.0:
            viol += 500.0 * (v1 - 11.0)
        if v2 > 11.0:
            viol += 500.0 * (v2 - 11.0)
        if v1 < 1.5:
            viol += 500.0 * (1.5 - v1)
        if v2 < 1.5:
            viol += 500.0 * (1.5 - v2)
        viol += 5.0 * abs(Q_des - Q_t)
        cost = 100.0 * travel + viol
        return (cost, h1_sp, h2_sp, h3_risk, h4_risk, v1, v2)
    best = None
    best_cost = None
    h1_min = max(0.02, sp_lo)
    h1_max = min(1.5, sp_hi)
    step = 0.01
    i = 0
    while True:
        h1_sp = h1_min + i * step
        if h1_sp > h1_max + 1e-9:
            break
        res = evaluate(h1_sp)
        if res is not None:
            if best_cost is None or res[0] < best_cost:
                best_cost = res[0]
                best = res
        i += 1
    if best is not None:
        h1_center = best[1]
        for j in range(-10, 11):
            h1_sp = h1_center + j * 0.001
            if h1_sp < h1_min or h1_sp > h1_max:
                continue
            res = evaluate(h1_sp)
            if res is not None:
                if res[0] < best_cost:
                    best_cost = res[0]
                    best = res
    if best is None:
        h1_fb = min(max(active_setpoints['h1'], sp_lo), sp_hi)
        h2_fb = min(max(active_setpoints['h2'], sp_lo), sp_hi)
        return {
            'diagnosis': 'no feasible setpoint found; holding active setpoints',
            'adjusted_setpoints': {'h1': h1_fb, 'h2': h2_fb}
        }
    _, h1_sp, h2_sp, h3_pred, h4_pred, v1_pred, v2_pred = best
    h1_sp = min(max(h1_sp, sp_lo), sp_hi)
    h2_sp = min(max(h2_sp, sp_lo), sp_hi)
    diag = 'model-based: G3=%.3f G4=%.3f d1=%.2f d2=%.2f Q_des=%.2f pred h3=%.2f h4=%.2f v1=%.2f v2=%.2f' % (G3_est, G4_est, d1_est, d2_est, Q_des, h3_pred, h4_pred, v1_pred, v2_pred)
    return {
        'diagnosis': diag,
        'adjusted_setpoints': {'h1': h1_sp, 'h2': h2_sp}
    }