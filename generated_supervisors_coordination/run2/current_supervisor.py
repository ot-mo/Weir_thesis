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

    Q_t = objectives["production_target"]
    h2_low, h2_high = objectives["h2_band"]
    upper_lim = objectives["upper_level_limit"]
    sp_lo, sp_hi = objectives["setpoint_limits"]

    n = len(telemetry_window)
    if n == 0:
        return {"diagnosis": "no telemetry; holding active setpoints",
                "adjusted_setpoints": {"h1": float(active_setpoints["h1"]),
                                       "h2": float(active_setpoints["h2"])}}

    def mean_of(data, key):
        tot = 0.0
        for s in data:
            tot += s[key]
        return tot / len(data)

    fast = telemetry_window[-5:] if n >= 5 else telemetry_window
    h3f = mean_of(fast, "h3")
    h4f = mean_of(fast, "h4")

    slow = telemetry_window[-10:] if n >= 10 else telemetry_window
    h1s = mean_of(slow, "h1")
    h2s = mean_of(slow, "h2")
    h3s = mean_of(slow, "h3")
    h4s = mean_of(slow, "h4")
    v1s = mean_of(slow, "v1")
    v2s = mean_of(slow, "v2")

    slope3 = 0.0
    slope4 = 0.0
    if n >= 20:
        wa = telemetry_window[-20:-10]
        wb = telemetry_window[-10:]
        slope3 = (mean_of(wb, "h3") - mean_of(wa, "h3")) / 10.0
        slope4 = (mean_of(wb, "h4") - mean_of(wa, "h4")) / 10.0

    def q_from_h(h, a):
        if h <= 0.0:
            return 0.0
        return 1000.0 * a * math.sqrt(2.0 * g * h)

    def h_from_q(q, a):
        if q <= 0.0:
            return 0.0
        return (q / (1000.0 * a)) ** 2 / (2.0 * g)

    q1s = q_from_h(h1s, a1)
    q2s = q_from_h(h2s, a2)
    q3s = q_from_h(h3s, a3)
    q4s = q_from_h(h4s, a4)

    if v1s > 0.5:
        B_est = q4s / v1s
    else:
        B_est = (1.0 - gamma1) * K1
    if v2s > 0.5:
        D_est = q3s / v2s
    else:
        D_est = (1.0 - gamma2) * K2
    B_est = max(B_est, 0.05)
    D_est = max(D_est, 0.05)

    alpha = gamma1 / (1.0 - gamma1)
    beta = gamma2 / (1.0 - gamma2)
    A_est = alpha * B_est
    C_est = beta * D_est
    d1_est = q1s - q3s - A_est * v1s
    d2_est = q2s - q4s - C_est * v2s

    def evaluate(h1_sp):
        if h1_sp < 0.02 or h1_sp > 1.5:
            return None
        q1c = q_from_h(h1_sp, a1)
        q2c = Q_t - q1c
        if q2c <= 0.01:
            return None
        h2_sp = h_from_q(q2c, a2)
        rhs1 = q1c - d1_est
        rhs2 = q2c - d2_est
        det = 1.0 - alpha * beta
        if abs(det) < 1e-9:
            return None
        q3c = (rhs1 - alpha * rhs2) / det
        q4c = (rhs2 - beta * rhs1) / det
        if q3c < -0.001 or q4c < -0.001:
            return None
        if q3c < 0.0:
            q3c = 0.0
        if q4c < 0.0:
            q4c = 0.0
        h3c = h_from_q(q3c, a3)
        h4c = h_from_q(q4c, a4)
        if B_est > 0.0:
            v1c = q4c / B_est
        else:
            v1c = 0.0
        if D_est > 0.0:
            v2c = q3c / D_est
        else:
            v2c = 0.0

        travel = abs(h1_sp - active_setpoints["h1"]) + abs(h2_sp - active_setpoints["h2"])
        viol = 0.0
        if h3c > upper_lim:
            viol += 10000.0 * (h3c - upper_lim)
        if h4c > upper_lim:
            viol += 10000.0 * (h4c - upper_lim)
        if h2_sp < h2_low:
            viol += 1000.0 * (h2_low - h2_sp)
        if h2_sp > h2_high:
            viol += 1000.0 * (h2_sp - h2_high)
        if v1c > 12.0:
            viol += 100.0 * (v1c - 12.0)
        if v2c > 12.0:
            viol += 100.0 * (v2c - 12.0)
        if v1c < 1.0:
            viol += 100.0 * (1.0 - v1c)
        if v2c < 1.0:
            viol += 100.0 * (1.0 - v2c)
        if h1_sp < 0.02:
            viol += 10000.0 * (0.02 - h1_sp)
        if h1_sp > 1.5:
            viol += 10000.0 * (h1_sp - 1.5)
        if h2_sp < 0.02:
            viol += 10000.0 * (0.02 - h2_sp)
        if h2_sp > 1.5:
            viol += 10000.0 * (h2_sp - 1.5)
        cost = travel + viol
        return cost, h1_sp, h2_sp, h3c, h4c, v1c, v2c

    best = None
    best_cost = None
    for i in range(149):
        h1_try = 0.02 + i * 0.01
        res = evaluate(h1_try)
        if res is not None:
            if best_cost is None or res[0] < best_cost:
                best_cost = res[0]
                best = res
    if best is not None:
        centre = best[1]
        for i in range(-10, 11):
            h1_try = centre + i * 0.001
            res = evaluate(h1_try)
            if res is not None and res[0] < best_cost:
                best_cost = res[0]
                best = res

    if best is None:
        h1_fb = min(max(active_setpoints["h1"], sp_lo), sp_hi)
        h2_fb = min(max(active_setpoints["h2"], sp_lo), sp_hi)
        return {"diagnosis": "no feasible setpoint from steady-state model; holding",
                "adjusted_setpoints": {"h1": h1_fb, "h2": h2_fb}}

    T_p = 30.0
    sq = math.sqrt(2.0 * g)
    dq3dh3 = 1000.0 * a3 * sq / (2.0 * math.sqrt(max(h3f, 0.01)))
    dq4dh4 = 1000.0 * a4 * sq / (2.0 * math.sqrt(max(h4f, 0.01)))
    damp3 = 1.0 + T_p * dq3dh3 / 1000.0
    damp4 = 1.0 + T_p * dq4dh4 / 1000.0
    base3 = slope3 * T_p / damp3
    base4 = slope4 * T_p / damp4
    if base3 > 0.05:
        base3 = 0.05
    if base3 < 0.0:
        base3 = 0.0
    if base4 > 0.05:
        base4 = 0.05
    if base4 < 0.0:
        base4 = 0.0
    r3 = h3f + base3 - upper_lim
    if r3 < 0.0:
        r3 = 0.0
    r4 = h4f + base4 - upper_lim
    if r4 < 0.0:
        r4 = 0.0

    shift = 0.7 * r4 - 0.7 * r3
    if shift > 0.12:
        shift = 0.12
    if shift < -0.12:
        shift = -0.12

    h1_sp = best[1] + shift
    q1c = q_from_h(h1_sp, a1)
    q2c = Q_t - q1c
    if q2c > 0.02:
        h2_sp = h_from_q(q2c, a2)
    else:
        h1_sp = best[1]
        h2_sp = best[2]

    if h2_sp > h2_high:
        h2_sp = h2_high
        q1c = Q_t - q_from_h(h2_sp, a2)
        if q1c > 0.02:
            h1_sp = h_from_q(q1c, a1)
    elif h2_sp < h2_low:
        h2_sp = h2_low
        q1c = Q_t - q_from_h(h2_sp, a2)
        if q1c > 0.02:
            h1_sp = h_from_q(q1c, a1)

    h1_sp = min(max(h1_sp, sp_lo), sp_hi)
    h2_sp = min(max(h2_sp, sp_lo), sp_hi)

    diag = "ss d1=%+.2f d2=%+.2f pred h3=%.2f h4=%.2f v1=%.1f v2=%.1f | risk h3=%.3f h4=%.3f shift=%+.3f" % (
        d1_est, d2_est, best[3], best[4], best[5], best[6], r3, r4, shift)
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1_sp, "h2": h2_sp}}
