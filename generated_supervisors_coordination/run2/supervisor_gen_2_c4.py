def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    g1 = 0.20
    g2 = 0.20
    g = 9.81
    Q_t_L = objectives["production_target"]
    Q_t = Q_t_L / 1000.0
    h2_low, h2_high = objectives["h2_band"]
    upper_lim = objectives["upper_level_limit"]
    sp_lo, sp_hi = objectives["setpoint_limits"]

    n = len(telemetry_window)
    if n < 2:
        return {"diagnosis": "insufficient data", "adjusted_setpoints": active_setpoints}

    M = 10 if n >= 10 else n
    recent = telemetry_window[-M:]
    h1 = sum(s["h1"] for s in recent) / M
    h2 = sum(s["h2"] for s in recent) / M
    h3 = sum(s["h3"] for s in recent) / M
    h4 = sum(s["h4"] for s in recent) / M
    v1 = sum(s["v1"] for s in recent) / M
    v2 = sum(s["v2"] for s in recent) / M

    def q_fun(h, a):
        if h <= 0.0:
            return 0.0
        return a * math.sqrt(2.0 * g * h)

    def h_fun(qq, a):
        if qq <= 0.0:
            return 0.0
        return (qq / a) ** 2 / (2.0 * g)

    q1 = q_fun(h1, a1)
    q2 = q_fun(h2, a2)
    q3 = q_fun(h3, a3)
    q4 = q_fun(h4, a4)

    def slope(key):
        m = 15 if n >= 15 else n
        samples = telemetry_window[-m:]
        t0 = samples[0]["time"]
        sumt = 0.0
        sumh = 0.0
        sumtt = 0.0
        sumth = 0.0
        for s in samples:
            t = s["time"] - t0
            val = s[key]
            sumt += t
            sumh += val
            sumtt += t * t
            sumth += t * val
        denom = m * sumtt - sumt * sumt
        if abs(denom) < 1e-12:
            return 0.0
        return (m * sumth - sumt * sumh) / denom

    dh1 = slope("h1")
    dh2 = slope("h2")
    dh3 = slope("h3")
    dh4 = slope("h4")

    k1_eff = 0.00085
    if v1 > 1.0:
        val = (dh4 + q4) / ((1.0 - g1) * v1)
        if val > 0.0:
            k1_eff = val
    k2_eff = 0.00095
    if v2 > 1.0:
        val = (dh3 + q3) / ((1.0 - g2) * v2)
        if val > 0.0:
            k2_eff = val
    k1_eff = min(max(k1_eff, 0.0003), 0.0015)
    k2_eff = min(max(k2_eff, 0.0003), 0.0015)

    d1 = dh1 + q1 - q3 - g1 * k1_eff * v1
    d2 = dh2 + q2 - q4 - g2 * k2_eff * v2
    d1 = min(max(d1, -0.01), 0.01)
    d2 = min(max(d2, -0.01), 0.01)

    A = g1 * k1_eff
    B = (1.0 - g2) * k2_eff
    C = (1.0 - g1) * k1_eff
    D = g2 * k2_eff
    det = A * D - B * C
    if abs(det) < 1e-12:
        return {"diagnosis": "degenerate model", "adjusted_setpoints": active_setpoints}

    def predict(h1s, h2s):
        q1s = q_fun(h1s, a1)
        q2s = q_fun(h2s, a2)
        rhs1 = q1s - d1
        rhs2 = q2s - d2
        v1p = (rhs1 * D - B * rhs2) / det
        v2p = (A * rhs2 - rhs1 * C) / det
        if v1p < 0.0:
            v1p = 0.0
        if v2p < 0.0:
            v2p = 0.0
        q3p = B * v2p
        q4p = C * v1p
        h3p = h_fun(q3p, a3)
        h4p = h_fun(q4p, a4)
        return v1p, v2p, h3p, h4p

    h1_act = min(max(active_setpoints["h1"], sp_lo), sp_hi)
    h2_act = min(max(active_setpoints["h2"], sp_lo), sp_hi)
    v1a, v2a, h3a, h4a = predict(h1_act, h2_act)
    Q_act = (q_fun(h1_act, a1) + q_fun(h2_act, a2)) * 1000.0

    safe = True
    if h3a > upper_lim - 0.02:
        safe = False
    if h4a > upper_lim - 0.02:
        safe = False
    if v1a > 11.5 or v2a > 11.5:
        safe = False
    if v1a < 1.2 or v2a < 1.2:
        safe = False
    if h2_act < h2_low - 0.005 or h2_act > h2_high + 0.005:
        safe = False
    if abs(Q_act - Q_t_L) > 0.2:
        safe = False

    if safe:
        return {"diagnosis": "holding; constraints safe", "adjusted_setpoints": {"h1": h1_act, "h2": h2_act}}

    best = None
    best_cost = None

    for dQ in range(-12, 13):
        Q_try = Q_t_L + dQ * 0.5
        if Q_try <= 0.0:
            continue
        for i in range(0, 73):
            h1s = 0.05 + i * 0.02
            q1s = q_fun(h1s, a1)
            q2s = Q_try / 1000.0 - q1s
            if q2s <= 0.0001:
                continue
            h2s = h_fun(q2s, a2)
            if h2s < 0.02 or h2s > 1.5:
                continue
            v1p, v2p, h3p, h4p = predict(h1s, h2s)
            travel = abs(h1s - h1_act) + abs(h2s - h2_act)
            Q_err = abs(Q_try - Q_t_L)
            cost = 100.0 * travel + 10.0 * Q_err
            if h3p > upper_lim:
                cost += 10000.0 * (h3p - upper_lim)
            if h4p > upper_lim:
                cost += 10000.0 * (h4p - upper_lim)
            if h2s < h2_low:
                cost += 200.0 * (h2_low - h2s)
            if h2s > h2_high:
                cost += 200.0 * (h2s - h2_high)
            if v1p > 12.0:
                cost += 500.0 * (v1p - 12.0)
            if v2p > 12.0:
                cost += 500.0 * (v2p - 12.0)
            if v1p < 1.0:
                cost += 500.0 * (1.0 - v1p)
            if v2p < 1.0:
                cost += 500.0 * (1.0 - v2p)
            if h1s < 0.02:
                cost += 10000.0 * (0.02 - h1s)
            if h2s < 0.02:
                cost += 10000.0 * (0.02 - h2s)
            if h1s > 1.5:
                cost += 10000.0 * (h1s - 1.5)
            if h2s > 1.5:
                cost += 10000.0 * (h2s - 1.5)
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = (h1s, h2s, h3p, h4p, v1p, v2p, Q_try)

    if best is None:
        return {"diagnosis": "no feasible setpoint found", "adjusted_setpoints": {"h1": h1_act, "h2": h2_act}}

    h1_best, h2_best, h3p, h4p, v1p, v2p, Q_best = best

    for i in range(-20, 21):
        h1s = h1_best + i * 0.001
        if h1s < 0.02 or h1s > 1.5:
            continue
        q1s = q_fun(h1s, a1)
        q2s = Q_best / 1000.0 - q1s
        if q2s <= 0.0001:
            continue
        h2s = h_fun(q2s, a2)
        if h2s < 0.02 or h2s > 1.5:
            continue
        v1p, v2p, h3p, h4p = predict(h1s, h2s)
        travel = abs(h1s - h1_act) + abs(h2s - h2_act)
        Q_err = abs(Q_best - Q_t_L)
        cost = 100.0 * travel + 10.0 * Q_err
        if h3p > upper_lim:
            cost += 10000.0 * (h3p - upper_lim)
        if h4p > upper_lim:
            cost += 10000.0 * (h4p - upper_lim)
        if h2s < h2_low:
            cost += 200.0 * (h2_low - h2s)
        if h2s > h2_high:
            cost += 200.0 * (h2s - h2_high)
        if v1p > 12.0:
            cost += 500.0 * (v1p - 12.0)
        if v2p > 12.0:
            cost += 500.0 * (v2p - 12.0)
        if v1p < 1.0:
            cost += 500.0 * (1.0 - v1p)
        if v2p < 1.0:
            cost += 500.0 * (1.0 - v2p)
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best = (h1s, h2s, h3p, h4p, v1p, v2p, Q_best)

    h1_best, h2_best, h3p, h4p, v1p, v2p, Q_best = best
    h1_best = min(max(h1_best, sp_lo), sp_hi)
    h2_best = min(max(h2_best, sp_lo), sp_hi)

    diag = "shift h1=%.3f h2=%.3f pred h3=%.2f h4=%.2f v1=%.2f v2=%.2f" % (h1_best, h2_best, h3p, h4p, v1p, v2p)
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1_best, "h2": h2_best}}