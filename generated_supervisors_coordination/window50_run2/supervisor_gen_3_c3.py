def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    gamma1 = 0.20
    gamma2 = 0.20
    g = 9.81
    Q_t = objectives["production_target"]
    h2_low, h2_high = objectives["h2_band"]
    upper_lim = objectives["upper_level_limit"]
    sp_lo, sp_hi = objectives["setpoint_limits"]

    n = len(telemetry_window)
    w = telemetry_window[-20:] if n >= 20 else telemetry_window
    m = len(w)

    sum_x = 0.0
    sum_x2 = 0.0
    for i in range(m):
        sum_x += i
        sum_x2 += i * i
    denom = m * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-9:
        denom = 1.0

    def slope(key):
        sum_y = 0.0
        sum_xy = 0.0
        for i, s in enumerate(w):
            y = s[key]
            sum_y += y
            sum_xy += i * y
        return (m * sum_xy - sum_x * sum_y) / denom

    dh1 = slope("h1")
    dh2 = slope("h2")
    dh3 = slope("h3")
    dh4 = slope("h4")

    recent = w[-5:] if len(w) >= 5 else w
    def avg(key):
        return sum(s[key] for s in recent) / len(recent)
    h1c = avg("h1")
    h2c = avg("h2")
    h3c = avg("h3")
    h4c = avg("h4")
    v1c = avg("v1")
    v2c = avg("v2")

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
        B_est = (q4c + 1000.0 * dh4) / v1c
    else:
        B_est = (1.0 - gamma1) * 0.85
    if v2c > 0.5:
        D_est = (q3c + 1000.0 * dh3) / v2c
    else:
        D_est = (1.0 - gamma2) * 0.95
    B_est = min(max(B_est, 0.35), 1.30)
    D_est = min(max(D_est, 0.40), 1.40)

    alpha = gamma1 / (1.0 - gamma1)
    beta = gamma2 / (1.0 - gamma2)
    A_est = alpha * B_est
    C_est = beta * D_est

    d1_est = 1000.0 * dh1 + q1c - q3c - A_est * v1c
    d2_est = 1000.0 * dh2 + q2c - q4c - C_est * v2c

    T_sim = 20.0
    dt = 1.0
    n_steps = int(T_sim / dt)

    def simulate_upper(v1, v2):
        v1 = min(max(v1, 1.0), 12.0)
        v2 = min(max(v2, 1.0), 12.0)
        h3 = h3c
        h4 = h4c
        viol = 0.0
        for _ in range(n_steps):
            out3 = a3 * math.sqrt(2.0 * g * h3) if h3 > 0 else 0.0
            in3 = D_est * v2 / 1000.0
            dh3 = in3 - out3
            out4 = a4 * math.sqrt(2.0 * g * h4) if h4 > 0 else 0.0
            in4 = B_est * v1 / 1000.0
            dh4 = in4 - out4
            h3 = h3 + dt * dh3
            h4 = h4 + dt * dh4
            if h3 > upper_lim:
                viol += (h3 - upper_lim)
            if h4 > upper_lim:
                viol += (h4 - upper_lim)
        return viol

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
        h3_ss = h_from_q(q3, a3)
        h4_ss = h_from_q(q4, a4)
        v1_ss = q4 / B_est if B_est > 0.1 else 0.0
        v2_ss = q3 / D_est if D_est > 0.1 else 0.0

        viol = 0.0
        if v1_ss > 12.0:
            viol += 200.0 * (v1_ss - 12.0)
        if v1_ss < 1.0:
            viol += 200.0 * (1.0 - v1_ss)
        if v2_ss > 12.0:
            viol += 200.0 * (v2_ss - 12.0)
        if v2_ss < 1.0:
            viol += 200.0 * (1.0 - v2_ss)

        viol_upper = simulate_upper(v1_ss, v2_ss)
        if h3_ss > upper_lim:
            viol_upper += 5.0 * (h3_ss - upper_lim)
        if h4_ss > upper_lim:
            viol_upper += 5.0 * (h4_ss - upper_lim)

        if h2_sp < h2_low:
            viol += 50.0 * (h2_low - h2_sp)
        if h2_sp > h2_high:
            viol += 50.0 * (h2_sp - h2_high)

        if h1_sp < 0.02:
            viol += 1e5 * (0.02 - h1_sp)
        if h1_sp > 1.5:
            viol += 1e5 * (h1_sp - 1.5)
        if h2_sp < 0.02:
            viol += 1e5 * (0.02 - h2_sp)
        if h2_sp > 1.5:
            viol += 1e5 * (h2_sp - 1.5)

        travel = abs(h1_sp - active_setpoints["h1"]) + abs(h2_sp - active_setpoints["h2"])
        cost = 100.0 * travel + viol + 200.0 * viol_upper
        return cost, h1_sp, h2_sp, h3_ss, h4_ss, v1_ss, v2_ss

    best = None
    best_cost = None
    for i in range(int((1.5 - 0.02) / 0.01) + 1):
        h1_sp = 0.02 + i * 0.01
        res = evaluate(h1_sp)
        if res is not None:
            cost = res[0]
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = res
    if best is not None:
        h1_center = best[1]
        for i in range(-15, 16):
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
            "adjusted_setpoints": {"h1": h1_fb, "h2": h2_fb},
        }

    _, h1_sp, h2_sp, h3_pred, h4_pred, v1_pred, v2_pred = best
    h1_sp = min(max(h1_sp, sp_lo), sp_hi)
    h2_sp = min(max(h2_sp, sp_lo), sp_hi)
    diag = (
        f"model-pred: d1={d1_est:.2f} d2={d2_est:.2f} "
        f"h3={h3_pred:.2f} h4={h4_pred:.2f} v1={v1_pred:.2f} v2={v2_pred:.2f}"
    )
    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"h1": h1_sp, "h2": h2_sp},
    }