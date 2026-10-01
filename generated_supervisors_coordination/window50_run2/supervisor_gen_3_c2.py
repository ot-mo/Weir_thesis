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
    Q_t = float(objectives['production_target'])
    h2_low, h2_high = objectives['h2_band']
    upper_lim = float(objectives['upper_level_limit'])
    sp_lo, sp_hi = objectives['setpoint_limits']
    n = len(telemetry_window)
    if n == 0:
        return {'diagnosis': 'empty telemetry', 'adjusted_setpoints': {'h1': active_setpoints['h1'], 'h2': active_setpoints['h2']}}
    m = min(15, n)
    recent = telemetry_window[-m:]
    avg = {}
    for key in ['h1','h2','h3','h4','v1','v2','production']:
        avg[key] = sum(s[key] for s in recent) / float(m)
    h1c = avg['h1']; h2c = avg['h2']; h3c = avg['h3']; h4c = avg['h4']
    v1c = avg['v1']; v2c = avg['v2']; Qc = avg['production']
    if n >= 20:
        first = telemetry_window[-20:-10]
        last = telemetry_window[-10:]
        def slope(k):
            return (sum(s[k] for s in last)/10.0 - sum(s[k] for s in first)/10.0) / 10.0
        dh1 = slope('h1'); dh2 = slope('h2')
        dh3 = slope('h3'); dh4 = slope('h4')
        dv1 = slope('v1'); dv2 = slope('v2')
    else:
        dh1 = dh2 = dh3 = dh4 = dv1 = dv2 = 0.0
    def clamp(x, lo, hi):
        if x < lo: return lo
        if x > hi: return hi
        return x
    dh3 = clamp(dh3, -0.05, 0.05)
    dh4 = clamp(dh4, -0.05, 0.05)
    dv1 = clamp(dv1, -0.5, 0.5)
    dv2 = clamp(dv2, -0.5, 0.5)
    def q_from_h(h, a):
        if h <= 0.0: return 0.0
        return 1000.0 * a * math.sqrt(2.0 * g * h)
    def h_from_q(q, a):
        if q <= 0.0: return 0.0
        return (q / (1000.0 * a)) ** 2 / (2.0 * g)
    q1c = q_from_h(h1c, a1)
    q2c = q_from_h(h2c, a2)
    q3c = q_from_h(h3c, a3)
    q4c = q_from_h(h4c, a4)
    B_nom = (1.0 - gamma1) * K1
    D_nom = (1.0 - gamma2) * K2
    if v1c > 2.0:
        B_meas = q4c / v1c
    else:
        B_meas = B_nom
    if v2c > 2.0:
        D_meas = q3c / v2c
    else:
        D_meas = D_nom
    B_est = clamp(B_meas, 0.2*B_nom, 2.0*B_nom)
    D_est = clamp(D_meas, 0.2*D_nom, 2.0*D_nom)
    alpha = gamma1 / (1.0 - gamma1)
    beta = gamma2 / (1.0 - gamma2)
    A_est = alpha * B_est
    C_est = beta * D_est
    d1_est = q1c - q3c - A_est * v1c
    d2_est = q2c - q4c - C_est * v2c
    Q_err = Q_t - Qc
    if abs(Q_err) < 0.05:
        Q_err = 0.0
    Q_eff = Q_t + clamp(0.6 * Q_err, -2.5, 2.5)
    margin = 0.035
    horizon = 20.0
    def evaluate(h1_sp):
        if h1_sp < 0.02 or h1_sp > 1.5:
            return None
        q1 = q_from_h(h1_sp, a1)
        q2 = Q_eff - q1
        if q2 <= 0.01:
            return None
        h2_sp = h_from_q(q2, a2)
        rhs1 = q1 - d1_est
        rhs2 = q2 - d2_est
        det = 1.0 - alpha * beta
        if abs(det) < 1e-9:
            return None
        q3 = (rhs1 - alpha * rhs2) / det
        q4 = (rhs2 - beta * rhs1) / det
        if q3 < -0.001 or q4 < -0.001:
            return None
        q3 = max(0.0, q3)
        q4 = max(0.0, q4)
        h3 = h_from_q(q3, a3)
        h4 = h_from_q(q4, a4)
        v1 = q4 / B_est if B_est > 0 else 0.0
        v2 = q3 / D_est if D_est > 0 else 0.0
        travel = abs(h1_sp - active_setpoints['h1']) + abs(h2_sp - active_setpoints['h2'])
        viol = 0.0
        if h3 > upper_lim - margin:
            viol += 20000.0 * (h3 - (upper_lim - margin))
        if h4 > upper_lim - margin:
            viol += 20000.0 * (h4 - (upper_lim - margin))
        dh3_pred = dh3 + D_est * (v2 - v2c)
        dh4_pred = dh4 + B_est * (v1 - v1c)
        h3_fut = h3c + dh3_pred * horizon
        h4_fut = h4c + dh4_pred * horizon
        if h3_fut > upper_lim - margin:
            viol += 5000.0 * (h3_fut - (upper_lim - margin))
        if h4_fut > upper_lim - margin:
            viol += 5000.0 * (h4_fut - (upper_lim - margin))
        if h3c > upper_lim:
            viol += 20000.0 * (h3c - upper_lim)
            viol += 200.0 * v2
        if h4c > upper_lim:
            viol += 20000.0 * (h4c - upper_lim)
            viol += 200.0 * v1
        if h2_sp < h2_low: viol += 2000.0 * (h2_low - h2_sp)
        if h2_sp > h2_high: viol += 2000.0 * (h2_sp - h2_high)
        if h2c < h2_low: viol += 2000.0 * (h2_low - h2c)
        if h2c > h2_high: viol += 2000.0 * (h2c - h2_high)
        v_margin = 0.4
        if v1 > 12.0 - v_margin: viol += 1000.0 * (v1 - (12.0 - v_margin))
        if v2 > 12.0 - v_margin: viol += 1000.0 * (v2 - (12.0 - v_margin))
        if v1 < 1.0 + v_margin: viol += 1000.0 * ((1.0 + v_margin) - v1)
        if v2 < 1.0 + v_margin: viol += 1000.0 * ((1.0 + v_margin) - v2)
        for val in (h1_sp, h2_sp, h1c, h2c):
            if val < 0.02: viol += 20000.0 * (0.02 - val)
            if val > 1.5: viol += 20000.0 * (val - 1.5)
        cost = travel + viol
        return cost, h1_sp, h2_sp, h3, h4, v1, v2
    best = None
    best_cost = None
    lo = max(0.02, sp_lo)
    hi = min(1.5, sp_hi)
    if hi < lo:
        lo, hi = 0.02, 1.5
    steps = int((hi - lo) / 0.01) + 1
    for i in range(steps):
        h1_sp = lo + i * 0.01
        if h1_sp > hi: break
        res = evaluate(h1_sp)
        if res is not None:
            cost = res[0]
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = res
    if best is not None:
        h1_center = best[1]
        for i in range(-10, 11):
            h1_sp = h1_center + i * 0.001
            if h1_sp < lo or h1_sp > hi: continue
            res = evaluate(h1_sp)
            if res is not None and res[0] < best_cost:
                best_cost = res[0]
                best = res
    if best is None:
        h1_fb = clamp(active_setpoints['h1'], sp_lo, sp_hi)
        h2_fb = clamp(active_setpoints['h2'], sp_lo, sp_hi)
        return {'diagnosis': 'no feasible setpoint; holding', 'adjusted_setpoints': {'h1': h1_fb, 'h2': h2_fb}}
    _, h1_sp, h2_sp, h3_pred, h4_pred, v1_pred, v2_pred = best
    h1_sp = clamp(h1_sp, sp_lo, sp_hi)
    h2_sp = clamp(h2_sp, sp_lo, sp_hi)
    diag = ('Qerr=%.2f Qeff=%.2f pred h3=%.2f h4=%.2f v1=%.2f v2=%.2f' %
            (Q_err, Q_eff, h3_pred, h4_pred, v1_pred, v2_pred))
    return {'diagnosis': diag, 'adjusted_setpoints': {'h1': h1_sp, 'h2': h2_sp}}
