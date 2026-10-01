def supervise(telemetry_window, active_setpoints, objectives):
    # Constants
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    gamma1 = 0.20
    gamma2 = 0.20
    K1 = 0.85  # L/(V*s)
    K2 = 0.95
    g = 9.81
    Q_t = objectives["production_target"]
    h2_low, h2_high = objectives["h2_band"]
    upper_lim = objectives["upper_level_limit"]
    sp_lo, sp_hi = objectives["setpoint_limits"]
    
    # Average recent samples to smooth derivatives and noise
    n = len(telemetry_window)
    recent = telemetry_window[-5:] if n >= 5 else telemetry_window
    m = len(recent)
    avg = {}
    for key in ["h1","h2","h3","h4","v1","v2"]:
        avg[key] = sum(s[key] for s in recent) / m
    h1c = avg["h1"]; h2c = avg["h2"]; h3c = avg["h3"]; h4c = avg["h4"]
    v1c = avg["v1"]; v2c = avg["v2"]
    
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
    
    # Estimate effective flow gains to upper tanks
    if v1c > 0.5:
        B_est = q4c / v1c
    else:
        B_est = (1.0 - gamma1) * K1
    if v2c > 0.5:
        D_est = q3c / v2c
    else:
        D_est = (1.0 - gamma2) * K2
    B_est = max(B_est, 0.05)
    D_est = max(D_est, 0.05)
    alpha = gamma1 / (1.0 - gamma1)
    beta = gamma2 / (1.0 - gamma2)
    A_est = alpha * B_est
    C_est = beta * D_est
    d1_est = q1c - q3c - A_est * v1c
    d2_est = q2c - q4c - C_est * v2c
    
    def evaluate(h1_sp):
        if h1_sp < 0.02 or h1_sp > 1.5:
            return None
        q1 = q_from_h(h1_sp, a1)
        q2 = Q_t - q1
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
        travel = abs(h1_sp - active_setpoints["h1"]) + abs(h2_sp - active_setpoints["h2"])
        viol = 0.0
        if h3 > upper_lim:
            viol += 10000.0 * (h3 - upper_lim)
        if h4 > upper_lim:
            viol += 10000.0 * (h4 - upper_lim)
        if h2_sp < h2_low:
            viol += 1000.0 * (h2_low - h2_sp)
        if h2_sp > h2_high:
            viol += 1000.0 * (h2_sp - h2_high)
        if v1 > 12.0:
            viol += 100.0 * (v1 - 12.0)
        if v2 > 12.0:
            viol += 100.0 * (v2 - 12.0)
        if v1 < 1.0:
            viol += 100.0 * (1.0 - v1)
        if v2 < 1.0:
            viol += 100.0 * (1.0 - v2)
        if h1_sp < 0.02:
            viol += 10000.0 * (0.02 - h1_sp)
        if h1_sp > 1.5:
            viol += 10000.0 * (h1_sp - 1.5)
        if h2_sp < 0.02:
            viol += 10000.0 * (0.02 - h2_sp)
        if h2_sp > 1.5:
            viol += 10000.0 * (h2_sp - 1.5)
        cost = travel + viol
        return cost, h1_sp, h2_sp, h3, h4, v1, v2
    
    best = None
    best_cost = None
    # Coarse grid over feasible h1 range
    for i in range(int((1.5 - 0.02) / 0.01) + 1):
        h1_sp = 0.02 + i * 0.01
        res = evaluate(h1_sp)
        if res is not None:
            cost = res[0]
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = res
    # Refine around best
    if best is not None:
        h1_center = best[1]
        for i in range(-10, 11):
            h1_sp = h1_center + i * 0.001
            res = evaluate(h1_sp)
            if res is not None:
                cost = res[0]
                if cost < best_cost:
                    best_cost = cost
                    best = res
    if best is None:
        h1_fb = min(max(active_setpoints["h1"], sp_lo), sp_hi)
        h2_fb = min(max(active_setpoints["h2"], sp_lo), sp_hi)
        return {
            "diagnosis": "no feasible setpoint found; holding active setpoints",
            "adjusted_setpoints": {"h1": h1_fb, "h2": h2_fb}
        }
    _, h1_sp, h2_sp, h3_pred, h4_pred, v1_pred, v2_pred = best
    h1_sp = min(max(h1_sp, sp_lo), sp_hi)
    h2_sp = min(max(h2_sp, sp_lo), sp_hi)
    diag = f"model-based: d1={d1_est:.2f} d2={d2_est:.2f} pred h3={h3_pred:.2f} h4={h4_pred:.2f} v1={v1_pred:.2f} v2={v2_pred:.2f}"
    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"h1": h1_sp, "h2": h2_sp}
    }