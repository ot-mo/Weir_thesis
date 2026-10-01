def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    gamma1 = 0.20
    gamma2 = 0.20
    g = 9.81
    sqrt2g = math.sqrt(2.0 * g)
    alpha1 = gamma1 / (1.0 - gamma1)
    alpha2 = gamma2 / (1.0 - gamma2)
    K1_nom = (1.0 - gamma1) * k1
    K2_nom = (1.0 - gamma2) * k2

    def sqrt2g_h(h):
        if h <= 0.0:
            return 0.0
        return math.sqrt(2.0 * g * h)

    def prod_Ls(h1, h2):
        if h1 <= 0.0 or h2 <= 0.0:
            return 0.0
        return 1000.0 * (a1 * math.sqrt(2.0 * g * h1) + a2 * math.sqrt(2.0 * g * h2))

    def lin_slope(times, vals):
        n = len(times)
        if n < 2:
            return 0.0
        mt = sum(times) / n
        mv = sum(vals) / n
        num = 0.0
        den = 0.0
        for t, v in zip(times, vals):
            dt = t - mt
            num += dt * (v - mv)
            den += dt * dt
        if den == 0.0:
            return 0.0
        return num / den

    last = telemetry_window[-1]
    h1m = last["h1"]
    h2m = last["h2"]
    h3m = last["h3"]
    h4m = last["h4"]
    v1m = last["v1"]
    v2m = last["v2"]

    window10 = telemetry_window[-10:] if len(telemetry_window) >= 10 else telemetry_window
    times = [s["time"] for s in window10]
    h1s = [s["h1"] for s in window10]
    h2s = [s["h2"] for s in window10]
    dh1dt = lin_slope(times, h1s)
    dh2dt = lin_slope(times, h2s)

    x3m = a3 * sqrt2g_h(h3m)
    x4m = a4 * sqrt2g_h(h4m)
    d1_est = dh1dt + a1 * sqrt2g_h(h1m) - x3m - alpha1 * x4m
    d2_est = dh2dt + a2 * sqrt2g_h(h2m) - x4m - alpha2 * x3m
    K1_eff = x4m / v1m if v1m > 0.5 else K1_nom
    K2_eff = x3m / v2m if v2m > 0.5 else K2_nom
    if K1_eff < 0.0001:
        K1_eff = 0.0001
    if K1_eff > 0.005:
        K1_eff = 0.005
    if K2_eff < 0.0001:
        K2_eff = 0.0001
    if K2_eff > 0.005:
        K2_eff = 0.005

    def predict(h1, h2):
        S1 = a1 * sqrt2g_h(h1) - d1_est
        S2 = a2 * sqrt2g_h(h2) - d2_est
        det = 1.0 - alpha1 * alpha2
        if det <= 1e-9:
            det = 1e-9
        x3 = (S1 - alpha1 * S2) / det
        x4 = (S2 - alpha2 * S1) / det
        if x3 < 0.0:
            x3 = 0.0
        if x4 < 0.0:
            x4 = 0.0
        h3 = (x3 / a3) ** 2 / (2.0 * g) if x3 > 0.0 else 0.0
        h4 = (x4 / a4) ** 2 / (2.0 * g) if x4 > 0.0 else 0.0
        v1 = x4 / K1_eff if K1_eff > 0.0 else 0.0
        v2 = x3 / K2_eff if K2_eff > 0.0 else 0.0
        return h3, h4, v1, v2

    Q_target = objectives["production_target"]
    h2_band = objectives["h2_band"]
    band_low = h2_band[0]
    band_high = h2_band[1]
    upper_limit = objectives["upper_level_limit"]
    sp_lo, sp_hi = objectives["setpoint_limits"]

    ah1 = active_setpoints["h1"]
    ah2 = active_setpoints["h2"]
    ah1c = min(sp_hi, max(sp_lo, ah1))
    ah2c = min(sp_hi, max(sp_lo, ah2))
    Q_active = prod_Ls(ah1c, ah2c)

    if abs(Q_active - Q_target) < 0.05:
        h3p, h4p, v1p, v2p = predict(ah1c, ah2c)
        safe = True
        if h3p > upper_limit - 0.02:
            safe = False
        if h4p > upper_limit - 0.02:
            safe = False
        if v1p > 11.8 or v1p < 1.2:
            safe = False
        if v2p > 11.8 or v2p < 1.2:
            safe = False
        if ah2c < band_low + 0.01 or ah2c > band_high - 0.01:
            safe = False
        if safe:
            return {
                "diagnosis": "on target, constraints OK, keeping setpoints",
                "adjusted_setpoints": {"h1": ah1c, "h2": ah2c},
            }

    margin = 0.03
    v_margin = 0.5

    def eval_candidate(h1, h2):
        h1c = min(sp_hi, max(sp_lo, h1))
        h2c = min(sp_hi, max(sp_lo, h2))
        Q_cand = prod_Ls(h1c, h2c)
        cost = 100.0 * (abs(h1c - ah1c) + abs(h2c - ah2c))
        cost += 10.0 * abs(Q_cand - Q_target)
        h3p, h4p, v1p, v2p = predict(h1c, h2c)
        if h3p > upper_limit - margin:
            cost += 10000.0 + 5000.0 * (h3p - (upper_limit - margin))
        if h4p > upper_limit - margin:
            cost += 10000.0 + 5000.0 * (h4p - (upper_limit - margin))
        if v1p > 12.0 - v_margin:
            cost += 10000.0 + 5000.0 * (v1p - (12.0 - v_margin))
        if v1p < 1.0 + v_margin:
            cost += 10000.0 + 5000.0 * ((1.0 + v_margin) - v1p)
        if v2p > 12.0 - v_margin:
            cost += 10000.0 + 5000.0 * (v2p - (12.0 - v_margin))
        if v2p < 1.0 + v_margin:
            cost += 10000.0 + 5000.0 * ((1.0 + v_margin) - v2p)
        if h2c < band_low + 0.01:
            cost += 10000.0 + 5000.0 * ((band_low + 0.01) - h2c)
        if h2c > band_high - 0.01:
            cost += 10000.0 + 5000.0 * (h2c - (band_high - 0.01))
        if h1c < 0.02 or h1c > 1.5:
            cost += 50000.0
        if h2c < 0.02 or h2c > 1.5:
            cost += 50000.0
        return cost, h1c, h2c

    best_cost = 1e18
    best_h1 = ah1c
    best_h2 = ah2c

    cost_a, h1_a, h2_a = eval_candidate(ah1c, ah2c)
    if cost_a < best_cost:
        best_cost = cost_a
        best_h1 = h1_a
        best_h2 = h2_a

    h2_min = max(0.05, sp_lo)
    h2_max = min(1.0, sp_hi)
    h2 = h2_min
    while h2 <= h2_max + 1e-9:
        q_m3 = Q_target / 1000.0
        s2 = math.sqrt(h2) if h2 > 0 else 0.0
        val = (q_m3 - a2 * sqrt2g * s2) / (a1 * sqrt2g)
        if val >= 0.0:
            h1 = val * val
            cost, h1c, h2c = eval_candidate(h1, h2)
            if cost < best_cost:
                best_cost = cost
                best_h1 = h1c
                best_h2 = h2c
        h2 += 0.01

    if best_h2 > h2_min and best_h2 < h2_max:
        for dh in [-0.005, -0.002, 0.0, 0.002, 0.005]:
            h2 = best_h2 + dh
            if h2 < h2_min or h2 > h2_max:
                continue
            q_m3 = Q_target / 1000.0
            s2 = math.sqrt(h2) if h2 > 0 else 0.0
            val = (q_m3 - a2 * sqrt2g * s2) / (a1 * sqrt2g)
            if val >= 0.0:
                h1 = val * val
                cost, h1c, h2c = eval_candidate(h1, h2)
                if cost < best_cost:
                    best_cost = cost
                    best_h1 = h1c
                    best_h2 = h2c

    if abs(best_h1 - ah1c) < 0.002 and abs(best_h2 - ah2c) < 0.002:
        best_h1 = ah1c
        best_h2 = ah2c

    diag = "target=%.2f Q_act=%.2f d1=%.4f d2=%.4f K1=%.5f K2=%.5f -> sp=(%.4f,%.4f)" % (
        Q_target, Q_active, d1_est, d2_est, K1_eff, K2_eff, best_h1, best_h2)
    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"h1": best_h1, "h2": best_h2},
    }