def supervise(telemetry_window, active_setpoints, objectives):
    # Constants
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    gamma1 = 0.20
    gamma2 = 0.20
    g = 9.81
    k1_nom = 0.85
    k2_nom = 0.95
    alpha = gamma1 / (1.0 - gamma1)
    beta = gamma2 / (1.0 - gamma2)
    det = 1.0 - alpha * beta
    
    Q_t = objectives["production_target"]
    h2_low, h2_high = objectives["h2_band"]
    upper_lim = objectives["upper_level_limit"]
    sp_lo, sp_hi = objectives["setpoint_limits"]
    active_h1 = active_setpoints["h1"]
    active_h2 = active_setpoints["h2"]
    
    n = len(telemetry_window)
    s_last = telemetry_window[-1]
    if n >= 5:
        s_first = telemetry_window[-5]
    else:
        s_first = telemetry_window[0]
    dt = s_last["time"] - s_first["time"]
    if dt <= 0:
        dt = 1.0
    dh1 = (s_last["h1"] - s_first["h1"]) / dt
    dh2 = (s_last["h2"] - s_first["h2"]) / dt
    dh3 = (s_last["h3"] - s_first["h3"]) / dt
    dh4 = (s_last["h4"] - s_first["h4"]) / dt
    h1_meas = s_last["h1"]
    h2_meas = s_last["h2"]
    h3_meas = s_last["h3"]
    h4_meas = s_last["h4"]
    v1_meas = s_last["v1"]
    v2_meas = s_last["v2"]
    
    def q_from_h(h, a):
        if h <= 0.0:
            return 0.0
        return 1000.0 * a * math.sqrt(2.0 * g * h)
    
    q1_meas = q_from_h(h1_meas, a1)
    q2_meas = q_from_h(h2_meas, a2)
    q3_meas = q_from_h(h3_meas, a3)
    q4_meas = q_from_h(h4_meas, a4)
    
    if v1_meas > 0.5:
        G1_est = (1000.0 * dh4 + q4_meas) / v1_meas
    else:
        G1_est = (1.0 - gamma1) * k1_nom
    if v2_meas > 0.5:
        G2_est = (1000.0 * dh3 + q3_meas) / v2_meas
    else:
        G2_est = (1.0 - gamma2) * k2_nom
    G1_est = max(0.0001, min(0.01, G1_est))
    G2_est = max(0.0001, min(0.01, G2_est))
    
    d1_est = 1000.0 * dh1 + q1_meas - q3_meas - alpha * G1_est * v1_meas
    d2_est = 1000.0 * dh2 + q2_meas - q4_meas - beta * G2_est * v2_meas
    d1_est = max(-30.0, min(30.0, d1_est))
    d2_est = max(-30.0, min(30.0, d2_est))
    
    w_Q = 20.0
    w_travel = 100.0
    w_band = 500.0
    w_upper_soft = 1000.0
    w_upper_hard = 10000.0
    w_pump = 500.0
    w_safety = 100000.0
    w_neg = 100.0
    
    soft_upper = upper_lim - 0.05
    soft_v = 11.0
    
    def eval_setpoint(h1_sp, h2_sp):
        if h1_sp < sp_lo or h1_sp > sp_hi or h2_sp < sp_lo or h2_sp > sp_hi:
            return None
        if h1_sp < 0.02 or h1_sp > 1.5 or h2_sp < 0.02 or h2_sp > 1.5:
            return None
        q1 = q_from_h(h1_sp, a1)
        q2 = q_from_h(h2_sp, a2)
        Q = q1 + q2
        rhs1 = q1 - d1_est
        rhs2 = q2 - d2_est
        q3 = (rhs1 - alpha * rhs2) / det
        q4 = (rhs2 - beta * rhs1) / det
        neg_pen = 0.0
        if q3 < 0.0:
            neg_pen += -q3 * w_neg
            q3 = 0.0
        if q4 < 0.0:
            neg_pen += -q4 * w_neg
            q4 = 0.0
        h3_sp = (q3 / (1000.0 * a3)) ** 2 / (2.0 * g) if q3 > 0 else 0.0
        h4_sp = (q4 / (1000.0 * a4)) ** 2 / (2.0 * g) if q4 > 0 else 0.0
        v1_sp = q4 / G1_est if G1_est > 0 else 0.0
        v2_sp = q3 / G2_est if G2_est > 0 else 0.0
        
        cost = 0.0
        cost += w_Q * abs(Q - Q_t)
        cost += w_travel * (abs(h1_sp - active_h1) + abs(h2_sp - active_h2))
        if h2_sp < h2_low:
            cost += w_band * (h2_low - h2_sp)
        elif h2_sp > h2_high:
            cost += w_band * (h2_sp - h2_high)
        if h3_sp > soft_upper:
            cost += w_upper_soft * (h3_sp - soft_upper)
        if h4_sp > soft_upper:
            cost += w_upper_soft * (h4_sp - soft_upper)
        if h3_sp > upper_lim:
            cost += w_upper_hard * (h3_sp - upper_lim)
        if h4_sp > upper_lim:
            cost += w_upper_hard * (h4_sp - upper_lim)
        if v1_sp > soft_v:
            cost += w_pump * (v1_sp - soft_v)
        if v2_sp > soft_v:
            cost += w_pump * (v2_sp - soft_v)
        if v1_sp < 1.5:
            cost += w_pump * (1.5 - v1_sp)
        if v2_sp < 1.5:
            cost += w_pump * (1.5 - v2_sp)
        if v1_sp > 12.0:
            cost += w_upper_hard * (v1_sp - 12.0)
        if v2_sp > 12.0:
            cost += w_upper_hard * (v2_sp - 12.0)
        if h1_sp < 0.02 or h1_sp > 1.5:
            cost += w_safety * (abs(h1_sp - 0.02) if h1_sp < 0.02 else abs(h1_sp - 1.5))
        if h2_sp < 0.02 or h2_sp > 1.5:
            cost += w_safety * (abs(h2_sp - 0.02) if h2_sp < 0.02 else abs(h2_sp - 1.5))
        cost += neg_pen
        return cost, h1_sp, h2_sp, Q, h3_sp, h4_sp, v1_sp, v2_sp
    
    best = None
    best_cost = None
    res = eval_setpoint(active_h1, active_h2)
    if res is not None:
        best = res
        best_cost = res[0]
    
    h1_min = 0.02
    h1_max = 1.5
    h2_min = 0.02
    h2_max = 1.5
    step = 0.02
    n1 = int((h1_max - h1_min) / step) + 1
    n2 = int((h2_max - h2_min) / step) + 1
    for i in range(n1):
        h1_sp = h1_min + i * step
        if h1_sp > h1_max:
            h1_sp = h1_max
        for j in range(n2):
            h2_sp = h2_min + j * step
            if h2_sp > h2_max:
                h2_sp = h2_max
            res = eval_setpoint(h1_sp, h2_sp)
            if res is not None:
                cost = res[0]
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best = res
    if best is not None:
        h1_c = best[1]
        h2_c = best[2]
        for refine_step in [0.005, 0.001]:
            for i in range(-10, 11):
                h1_sp = h1_c + i * refine_step
                for j in range(-10, 11):
                    h2_sp = h2_c + j * refine_step
                    res = eval_setpoint(h1_sp, h2_sp)
                    if res is not None:
                        cost = res[0]
                        if cost < best_cost:
                            best_cost = cost
                            best = res
            h1_c = best[1]
            h2_c = best[2]
    
    if best is None:
        h1_out = min(max(active_h1, sp_lo), sp_hi)
        h2_out = min(max(active_h2, sp_lo), sp_hi)
        return {
            "diagnosis": "no feasible setpoint found; holding active setpoints",
            "adjusted_setpoints": {"h1": h1_out, "h2": h2_out}
        }
    
    _, h1_out, h2_out, Q_pred, h3_pred, h4_pred, v1_pred, v2_pred = best
    h1_out = min(max(h1_out, sp_lo), sp_hi)
    h2_out = min(max(h2_out, sp_lo), sp_hi)
    diag = f"model-based: d1={d1_est:.2f} d2={d2_est:.2f} G1={G1_est:.5f} G2={G2_est:.5f} pred Q={Q_pred:.2f} h3={h3_pred:.2f} h4={h4_pred:.2f} v1={v1_pred:.2f} v2={v2_pred:.2f}"
    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"h1": h1_out, "h2": h2_out}
    }
