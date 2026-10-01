def supervise(telemetry_window, active_setpoints, objectives):
    a1=0.0035; a2=0.003; a3=0.002; a4=0.0025
    gamma1=0.20; gamma2=0.20
    K1_nom=0.85; K2_nom=0.95
    g=9.81
    Q_t = objectives["production_target"]
    h2_low, h2_high = objectives["h2_band"]
    upper_lim = objectives["upper_level_limit"]
    sp_lo, sp_hi = objectives["setpoint_limits"]

    n = len(telemetry_window)
    recent5 = telemetry_window[-5:] if n >=5 else telemetry_window
    m = len(recent5)
    h1c = sum(s["h1"] for s in recent5)/m
    h2c = sum(s["h2"] for s in recent5)/m
    h3c = sum(s["h3"] for s in recent5)/m
    h4c = sum(s["h4"] for s in recent5)/m
    v1c = sum(s["v1"] for s in recent5)/m
    v2c = sum(s["v2"] for s in recent5)/m
    Qc = sum(s["production"] for s in recent5)/m

    recent10 = telemetry_window[-10:] if n >=10 else telemetry_window
    if len(recent10) >= 2:
        t0 = recent10[0]["time"]
        t1 = recent10[-1]["time"]
        dt = t1 - t0
        if dt <= 0: dt = 9.0
        dh1 = (recent10[-1]["h1"] - recent10[0]["h1"]) / dt
        dh2 = (recent10[-1]["h2"] - recent10[0]["h2"]) / dt
        dh3 = (recent10[-1]["h3"] - recent10[0]["h3"]) / dt
        dh4 = (recent10[-1]["h4"] - recent10[0]["h4"]) / dt
    else:
        dh1=dh2=dh3=dh4=0.0

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

    F4 = dh4 + q4c
    if v1c > 0.5:
        k1_eff = F4 / ((1.0 - gamma1) * v1c)
    else:
        k1_eff = K1_nom
    if k1_eff < 0.3: k1_eff = 0.3
    if k1_eff > 1.5: k1_eff = 1.5

    F3 = dh3 + q3c
    if v2c > 0.5:
        k2_eff = F3 / ((1.0 - gamma2) * v2c)
    else:
        k2_eff = K2_nom
    if k2_eff < 0.3: k2_eff = 0.3
    if k2_eff > 1.5: k2_eff = 1.5

    d1_est = dh1 + q1c - q3c - gamma1 * k1_eff * v1c
    d2_est = dh2 + q2c - q4c - gamma2 * k2_eff * v2c

    alpha = gamma1 / (1.0 - gamma1)
    beta = gamma2 / (1.0 - gamma2)
    det = 1.0 - alpha * beta

    Q_eff = Q_t + 0.3 * (Q_t - Qc)
    if Q_eff < 0.5 * Q_t: Q_eff = 0.5 * Q_t
    if Q_eff > 1.5 * Q_t: Q_eff = 1.5 * Q_t

    def evaluate(h1_sp, Q_target):
        if h1_sp < 0.02 or h1_sp > 1.5:
            return None
        q1 = q_from_h(h1_sp, a1)
        q2 = Q_target - q1
        if q2 <= 0.01:
            return None
        h2_sp = h_from_q(q2, a2)
        if h2_sp < 0.02 or h2_sp > 1.5:
            return None
        rhs1 = q1 - d1_est
        rhs2 = q2 - d2_est
        q3 = (rhs1 - alpha * rhs2) / det
        q4 = (rhs2 - beta * rhs1) / det
        if q3 < -0.001 or q4 < -0.001:
            return None
        q3 = max(0.0, q3)
        q4 = max(0.0, q4)
        h3 = h_from_q(q3, a3)
        h4 = h_from_q(q4, a4)
        v1 = q4 / ((1.0 - gamma1) * k1_eff) if k1_eff > 0 else 0.0
        v2 = q3 / ((1.0 - gamma2) * k2_eff) if k2_eff > 0 else 0.0
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
        if h3c > upper_lim:
            viol += 50.0 * (h3c - upper_lim) * v2
        if h4c > upper_lim:
            viol += 50.0 * (h4c - upper_lim) * v1
        cost = travel + viol
        return cost, h1_sp, h2_sp, h3, h4, v1, v2

    best = None
    best_cost = None
    for i in range(int((1.5 - 0.02) / 0.01) + 1):
        h1_sp = 0.02 + i * 0.01
        res = evaluate(h1_sp, Q_eff)
        if res is not None:
            cost = res[0]
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = res
    if best is not None:
        h1_center = best[1]
        for i in range(-10, 11):
            h1_sp = h1_center + i * 0.001
            res = evaluate(h1_sp, Q_eff)
            if res is not None:
                cost = res[0]
                if cost < best_cost:
                    best_cost = cost
                    best = res
    if best is None:
        for i in range(int((1.5 - 0.02) / 0.01) + 1):
            h1_sp = 0.02 + i * 0.01
            res = evaluate(h1_sp, Q_t)
            if res is not None:
                cost = res[0]
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best = res
        if best is not None:
            h1_center = best[1]
            for i in range(-10, 11):
                h1_sp = h1_center + i * 0.001
                res = evaluate(h1_sp, Q_t)
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
    diag = f"model-based: d1={d1_est:.2f} d2={d2_est:.2f} k1e={k1_eff:.3f} k2e={k2_eff:.3f} Qc={Qc:.2f} Qeff={Q_eff:.2f} pred h3={h3_pred:.2f} h4={h4_pred:.2f} v1={v1_pred:.2f} v2={v2_pred:.2f}"
    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"h1": h1_sp, "h2": h2_sp}
    }