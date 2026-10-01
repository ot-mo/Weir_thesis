def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    gamma1 = 0.20
    gamma2 = 0.20
    alpha = gamma1 / (1.0 - gamma1)
    beta = gamma2 / (1.0 - gamma2)
    g = 9.81
    Q_t = objectives["production_target"]
    h2_low, h2_high = objectives["h2_band"]
    upper_lim = objectives["upper_level_limit"]
    sp_lo, sp_hi = objectives["setpoint_limits"]

    n = len(telemetry_window)
    if n == 0:
        return {"diagnosis": "no data", "adjusted_setpoints": active_setpoints}

    N = 20 if n >= 20 else n
    win = telemetry_window[-N:]
    times = [s["time"] for s in win]
    t_mean = sum(times) / N

    def slope(vals):
        v_mean = sum(vals) / N
        num = sum((times[i] - t_mean) * (vals[i] - v_mean) for i in range(N))
        den = sum((times[i] - t_mean) ** 2 for i in range(N))
        return num / den if den > 1e-9 else 0.0

    h1_list = [s["h1"] for s in win]
    h2_list = [s["h2"] for s in win]
    h3_list = [s["h3"] for s in win]
    h4_list = [s["h4"] for s in win]
    v1_list = [s["v1"] for s in win]
    v2_list = [s["v2"] for s in win]

    h1c = sum(h1_list) / N
    h2c = sum(h2_list) / N
    h3c = sum(h3_list) / N
    h4c = sum(h4_list) / N
    v1c = sum(v1_list) / N
    v2c = sum(v2_list) / N

    dh1 = slope(h1_list)
    dh2 = slope(h2_list)
    dh3 = slope(h3_list)
    dh4 = slope(h4_list)

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
        B_est = (q4c + dh4) / v1c
    else:
        B_est = (1.0 - gamma1) * 0.85
    if v2c > 0.5:
        D_est = (q3c + dh3) / v2c
    else:
        D_est = (1.0 - gamma2) * 0.95
    B_est = min(max(B_est, 0.2), 2.0)
    D_est = min(max(D_est, 0.2), 2.0)

    A_est = alpha * B_est
    C_est = beta * D_est

    d1_est = dh1 + q1c - q3c - A_est * v1c
    d2_est = dh2 + q2c - q4c - C_est * v2c

    margin_h = 0.03
    margin_v = 0.5
    v_max = 12.0
    v_min = 1.0
    T_pred = 30.0

    eff_lim3 = upper_lim - margin_h
    if dh3 > 0.0:
        eff_lim3 -= dh3 * T_pred
    eff_lim4 = upper_lim - margin_h
    if dh4 > 0.0:
        eff_lim4 -= dh4 * T_pred

    cur_exc3 = max(0.0, h3c - (upper_lim - margin_h))
    cur_exc4 = max(0.0, h4c - (upper_lim - margin_h))

    def evaluate(h1_sp):
        if h1_sp < sp_lo or h1_sp > sp_hi:
            return None
        q1_sp = q_from_h(h1_sp, a1)
        q2_sp = Q_t - q1_sp
        if q2_sp <= 0.01:
            return None
        h2_sp = h_from_q(q2_sp, a2)
        det = 1.0 - alpha * beta
        rhs1 = q1_sp - d1_est
        rhs2 = q2_sp - d2_est
        q3 = (rhs1 - alpha * rhs2) / det
        q4 = (rhs2 - beta * rhs1) / det
        if q3 < -0.05 or q4 < -0.05:
            return None
        q3p = max(0.0, q3)
        q4p = max(0.0, q4)
        h3_pred = h_from_q(q3p, a3)
        h4_pred = h_from_q(q4p, a4)
        v1_pred = q4p / B_est if B_est > 0.0 else 0.0
        v2_pred = q3p / D_est if D_est > 0.0 else 0.0

        cost = 100.0 * (abs(h1_sp - active_setpoints["h1"]) + abs(h2_sp - active_setpoints["h2"]))

        if h3_pred > eff_lim3:
            cost += 2000.0 * (h3_pred - eff_lim3)
        if h4_pred > eff_lim4:
            cost += 2000.0 * (h4_pred - eff_lim4)

        if h2_sp < h2_low:
            cost += 2000.0 * (h2_low - h2_sp)
        if h2_sp > h2_high:
            cost += 2000.0 * (h2_sp - h2_high)

        if h1_sp < 0.02:
            cost += 10000.0 * (0.02 - h1_sp)
        if h1_sp > 1.5:
            cost += 10000.0 * (h1_sp - 1.5)
        if h2_sp < 0.02:
            cost += 10000.0 * (0.02 - h2_sp)
        if h2_sp > 1.5:
            cost += 10000.0 * (h2_sp - 1.5)

        if v1_pred > v_max - margin_v:
            cost += 1000.0 * (v1_pred - (v_max - margin_v))
        if v1_pred < v_min + margin_v:
            cost += 1000.0 * ((v_min + margin_v) - v1_pred)
        if v2_pred > v_max - margin_v:
            cost += 1000.0 * (v2_pred - (v_max - margin_v))
        if v2_pred < v_min + margin_v:
            cost += 1000.0 * ((v_min + margin_v) - v2_pred)

        if cur_exc3 > 0.0:
            cost += 5000.0 * cur_exc3 * max(0.0, v2_pred - v2c)
        if cur_exc4 > 0.0:
            cost += 5000.0 * cur_exc4 * max(0.0, v1_pred - v1c)

        if q3 < 0.0:
            cost += 1000.0 * (-q3)
        if q4 < 0.0:
            cost += 1000.0 * (-q4)

        return cost, h1_sp, h2_sp, h3_pred, h4_pred, v1_pred, v2_pred

    best = None
    best_cost = None
    step = 0.01
    i = 0
    while True:
        h1_sp = sp_lo + i * step
        if h1_sp > sp_hi + 1e-9:
            break
        res = evaluate(h1_sp)
        if res is not None:
            cost = res[0]
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = res
        i += 1

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
