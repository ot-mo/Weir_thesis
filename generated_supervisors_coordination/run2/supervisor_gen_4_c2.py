def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    g = 9.81
    gam1 = 0.20
    gam2 = 0.20
    k1n = 0.00085
    k2n = 0.00095
    Q_t = objectives['production_target']
    h2_low, h2_high = objectives['h2_band']
    upper_lim = objectives['upper_level_limit']
    sp_lo, sp_hi = objectives['setpoint_limits']
    n = len(telemetry_window)
    if n < 2:
        return {'diagnosis': 'insufficient data', 'adjusted_setpoints': {'h1': active_setpoints['h1'], 'h2': active_setpoints['h2']}}
    kk = min(5, n)
    rec = telemetry_window[-kk:]
    def avgf(key):
        return sum(s[key] for s in rec) / kk
    h1c = avgf('h1')
    h2c = avgf('h2')
    h3c = avgf('h3')
    h4c = avgf('h4')
    v1c = avgf('v1')
    v2c = avgf('v2')
    Qc = avgf('production')
    ms = min(20, n)
    seg = telemetry_window[-ms:]
    dt = seg[-1]['time'] - seg[0]['time']
    if dt <= 0.0:
        dt = 1.0
    def sl(key):
        return (seg[-1][key] - seg[0][key]) / dt
    s_h2 = sl('h2')
    s_h3 = sl('h3')
    s_h4 = sl('h4')
    def qh(h, a):
        if h <= 0.0:
            return 0.0
        return a * math.sqrt(2.0 * g * h)
    def hq(q, a):
        if q <= 0.0:
            return 0.0
        return (q / a) ** 2 / (2.0 * g)
    q1c = qh(h1c, a1)
    q2c = qh(h2c, a2)
    q3c = qh(h3c, a3)
    q4c = qh(h4c, a4)
    B_nom = (1.0 - gam1) * k1n
    D_nom = (1.0 - gam2) * k2n
    if v1c > 1.0:
        B_est = q4c / v1c
    else:
        B_est = B_nom
    if v2c > 1.0:
        D_est = q3c / v2c
    else:
        D_est = D_nom
    B_est = min(max(B_est, 0.5 * B_nom), 1.5 * B_nom)
    D_est = min(max(D_est, 0.5 * D_nom), 1.5 * D_nom)
    alpha = gam1 / (1.0 - gam1)
    beta = gam2 / (1.0 - gam2)
    det = 1.0 - alpha * beta
    if abs(det) < 1e-9:
        det = 1e-9
    d1_est = q1c - q3c - gam1 * k1n * v1c
    d2_est = q2c - q4c - gam2 * k2n * v2c
    q_bias = 0.5 * (Q_t - Qc)
    if q_bias > 1.5:
        q_bias = 1.5
    if q_bias < -1.5:
        q_bias = -1.5
    Q_eff = Q_t + q_bias
    T_h = 20.0
    margin3 = s_h3 * T_h
    if margin3 < 0.0:
        margin3 = 0.0
    if margin3 > 0.15:
        margin3 = 0.15
    margin4 = s_h4 * T_h
    if margin4 < 0.0:
        margin4 = 0.0
    if margin4 > 0.15:
        margin4 = 0.15
    lim3_eff = upper_lim - margin3
    lim4_eff = upper_lim - margin4
    m2hi = s_h2 * T_h
    if m2hi < 0.0:
        m2hi = 0.0
    if m2hi > 0.08:
        m2hi = 0.08
    m2lo = -s_h2 * T_h
    if m2lo < 0.0:
        m2lo = 0.0
    if m2lo > 0.08:
        m2lo = 0.08
    act_h1 = active_setpoints['h1']
    act_h2 = active_setpoints['h2']
    def evaluate(h1_sp):
        if h1_sp < 0.02 or h1_sp > 1.5:
            return None
        q1 = qh(h1_sp, a1)
        q2 = Q_eff / 1000.0 - q1
        if q2 <= 0.005:
            return None
        h2_sp = hq(q2, a2)
        rhs1 = q1 - d1_est
        rhs2 = q2 - d2_est
        q3 = (rhs1 - alpha * rhs2) / det
        q4 = (rhs2 - beta * rhs1) / det
        if q3 < -0.0005 or q4 < -0.0005:
            return None
        if q3 < 0.0:
            q3 = 0.0
        if q4 < 0.0:
            q4 = 0.0
        h3 = hq(q3, a3)
        h4 = hq(q4, a4)
        v1 = q4 / B_est
        v2 = q3 / D_est
        travel = abs(h1_sp - act_h1) + abs(h2_sp - act_h2)
        viol = 0.0
        if h3 > lim3_eff:
            viol += 4000.0 * (h3 - lim3_eff)
        if h4 > lim4_eff:
            viol += 4000.0 * (h4 - lim4_eff)
        if h2_sp > h2_high - m2hi:
            viol += 800.0 * (h2_sp - (h2_high - m2hi))
        if h2_sp < h2_low + m2lo:
            viol += 800.0 * ((h2_low + m2lo) - h2_sp)
        if v1 > 12.0:
            viol += 300.0 * (v1 - 12.0)
        if v2 > 12.0:
            viol += 300.0 * (v2 - 12.0)
        if v1 < 1.0:
            viol += 300.0 * (1.0 - v1)
        if v2 < 1.0:
            viol += 300.0 * (1.0 - v2)
        if h1_sp < 0.02:
            viol += 10000.0 * (0.02 - h1_sp)
        if h2_sp < 0.02:
            viol += 10000.0 * (0.02 - h2_sp)
        cost = travel + viol
        return (cost, h1_sp, h2_sp, h3, h4, v1, v2)
    lo = 0.02
    hi = sp_hi
    if hi > 1.5:
        hi = 1.5
    if hi < lo + 0.01:
        hi = lo + 0.01
    best = None
    best_cost = None
    N = 110
    for i in range(N + 1):
        h1_sp = lo + (hi - lo) * i / N
        res = evaluate(h1_sp)
        if res is not None:
            if best_cost is None or res[0] < best_cost:
                best_cost = res[0]
                best = res
    if best is not None:
        hc = best[1]
        for j in range(-20, 21):
            h1_try = hc + j * 0.001
            res = evaluate(h1_try)
            if res is not None and res[0] < best_cost:
                best_cost = res[0]
                best = res
    if best is None:
        h1f = min(max(act_h1, sp_lo), sp_hi)
        h2f = min(max(act_h2, sp_lo), sp_hi)
        return {'diagnosis': 'no feasible setpoint; holding', 'adjusted_setpoints': {'h1': h1f, 'h2': h2f}}
    h1_out = best[1]
    h2_out = best[2]
    h1_out = min(max(h1_out, sp_lo), sp_hi)
    h2_out = min(max(h2_out, sp_lo), sp_hi)
    diag = 'ss+slope: lim3=%.3f lim4=%.3f sl3=%.4f sl4=%.4f v1=%.2f v2=%.2f' % (lim3_eff, lim4_eff, s_h3, s_h4, best[5], best[6])
    return {'diagnosis': diag, 'adjusted_setpoints': {'h1': round(h1_out, 4), 'h2': round(h2_out, 4)}}