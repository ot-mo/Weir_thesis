def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    g = 9.81
    g1n = 0.20
    g2n = 0.20
    k1n = 0.00085
    k2n = 0.00095
    u1n = (1.0 - g1n) * k1n
    u2n = (1.0 - g2n) * k2n
    r1 = g1n / (1.0 - g1n)
    r2 = g2n / (1.0 - g2n)
    Vmax = 12.0

    h_lim = float(objectives["upper_level_limit"])
    h2_lo = float(objectives["h2_band"][0])
    h2_hi = float(objectives["h2_band"][1])
    sp_lo = float(objectives["setpoint_limits"][0])
    sp_hi = float(objectives["setpoint_limits"][1])
    Q_tgt = float(objectives["production_target"]) * 0.001

    h1_cur = float(active_setpoints["h1"])
    h2_cur = float(active_setpoints["h2"])

    n = len(telemetry_window)
    if n < 5:
        return {"diagnosis": "insufficient telemetry; holding setpoints",
                "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur}}

    two_g = 2.0 * g

    def F1f(h):
        return a1 * math.sqrt(two_g * h) if h > 0.0 else 0.0
    def F2f(h):
        return a2 * math.sqrt(two_g * h) if h > 0.0 else 0.0
    def F3f(h):
        return a3 * math.sqrt(two_g * h) if h > 0.0 else 0.0
    def F4f(h):
        return a4 * math.sqrt(two_g * h) if h > 0.0 else 0.0

    h1_a = float(telemetry_window[0]["h1"])
    h1_b = float(telemetry_window[-1]["h1"])
    h2_a = float(telemetry_window[0]["h2"])
    h2_b = float(telemetry_window[-1]["h2"])
    h3_a = float(telemetry_window[0]["h3"])
    h3_b = float(telemetry_window[-1]["h3"])
    h4_a = float(telemetry_window[0]["h4"])
    h4_b = float(telemetry_window[-1]["h4"])
    T = float(telemetry_window[-1]["time"]) - float(telemetry_window[0]["time"])
    if T <= 0.0:
        T = 1.0

    sF1 = 0.0
    sF2 = 0.0
    sF3 = 0.0
    sF4 = 0.0
    sv1 = 0.0
    sv2 = 0.0
    for s in telemetry_window:
        sF1 += F1f(float(s["h1"]))
        sF2 += F2f(float(s["h2"]))
        sF3 += F3f(float(s["h3"]))
        sF4 += F4f(float(s["h4"]))
        sv1 += float(s["v1"])
        sv2 += float(s["v2"])
    aF1 = sF1 / n
    aF2 = sF2 / n
    aF3 = sF3 / n
    aF4 = sF4 / n
    av1 = sv1 / n
    av2 = sv2 / n

    if av1 > 0.3:
        u1 = ((h4_b - h4_a) + aF4 * T) / (av1 * T)
    else:
        u1 = u1n
    if av2 > 0.3:
        u2 = ((h3_b - h3_a) + aF3 * T) / (av2 * T)
    else:
        u2 = u2n
    if u1 < 0.35 * u1n:
        u1 = 0.35 * u1n
    if u1 > 1.60 * u1n:
        u1 = 1.60 * u1n
    if u2 < 0.35 * u2n:
        u2 = 0.35 * u2n
    if u2 > 1.60 * u2n:
        u2 = 1.60 * u2n

    d1 = ((h1_b - h1_a) + aF1 * T - aF3 * T - r1 * u1 * av1 * T) / T
    d2 = ((h2_b - h2_a) + aF2 * T - aF4 * T - r2 * u2 * av2 * T) / T
    if d1 < -6e-3:
        d1 = -6e-3
    if d1 > 6e-3:
        d1 = 6e-3
    if d2 < -6e-3:
        d2 = -6e-3
    if d2 > 6e-3:
        d2 = 6e-3

    denom = 1.0 - r1 * r2
    if denom < 0.05:
        denom = 0.05

    def predict(h1s, h2s):
        F1 = F1f(h1s)
        F2 = F2f(h2s)
        S1 = F1 - d1
        S2 = F2 - d2
        F4 = (S2 - r2 * S1) / denom
        F3 = S1 - r1 * F4
        if F3 < 0.0:
            F3 = 0.0
        if F4 < 0.0:
            F4 = 0.0
        if u1 > 1e-12:
            v1 = F4 / u1
        else:
            v1 = Vmax
        if u2 > 1e-12:
            v2 = F3 / u2
        else:
            v2 = Vmax
        sat1 = v1 > Vmax
        sat2 = v2 > Vmax
        F1_act = F1
        F2_act = F2
        if sat1 and sat2:
            F4 = u1 * Vmax
            F3 = u2 * Vmax
            v1 = Vmax
            v2 = Vmax
            F1_act = F3 + r1 * F4 + d1
            F2_act = F4 + r2 * F3 + d2
        elif sat2:
            F3 = u2 * Vmax
            v2 = Vmax
            F4 = F2 - r2 * F3 - d2
            if F4 < 0.0:
                F4 = 0.0
            if u1 > 1e-12:
                v1 = F4 / u1
            else:
                v1 = Vmax
            if v1 > Vmax:
                v1 = Vmax
                F4 = u1 * Vmax
            F1_act = F3 + r1 * F4 + d1
        elif sat1:
            F4 = u1 * Vmax
            v1 = Vmax
            F3 = F1 - r1 * F4 - d1
            if F3 < 0.0:
                F3 = 0.0
            if u2 > 1e-12:
                v2 = F3 / u2
            else:
                v2 = Vmax
            if v2 > Vmax:
                v2 = Vmax
                F3 = u2 * Vmax
            F2_act = F4 + r2 * F3 + d2
        if F1_act < 0.0:
            F1_act = 0.0
        if F2_act < 0.0:
            F2_act = 0.0
        h3p = (F3 / a3) ** 2 / two_g
        h4p = (F4 / a4) ** 2 / two_g
        h1p = (F1_act / a1) ** 2 / two_g
        h2p = (F2_act / a2) ** 2 / two_g
        Q_act = F1_act + F2_act
        return h3p, h4p, h1p, h2p, v1, v2, Q_act

    def h2_for_Q(h1s):
        q1 = F1f(h1s)
        q2 = Q_tgt - q1
        if q2 <= 1e-8:
            return None
        return (q2 / a2) ** 2 / two_g

    def cost(h1s, h2s):
        h3p, h4p, h1p, h2p, v1, v2, Q_act = predict(h1s, h2s)
        c = 0.0
        c += 3000.0 * max(0.0, h3p - (h_lim - 0.01))
        c += 3000.0 * max(0.0, h4p - (h_lim - 0.01))
        c += 2000.0 * max(0.0, v1 - 11.5)
        c += 2000.0 * max(0.0, v2 - 11.5)
        c += 10000.0 * max(0.0, (h2_lo + 0.005) - h2p)
        c += 10000.0 * max(0.0, h2p - (h2_hi - 0.005))
        c += 100000.0 * max(0.0, 0.03 - h1p)
        c += 100000.0 * max(0.0, h1p - 1.45)
        c += 100000.0 * max(0.0, 0.03 - h2p)
        c += 100000.0 * max(0.0, h2p - 1.45)
        c += 300000.0 * abs(Q_act - Q_tgt)
        c += 100.0 * (abs(h1s - h1_cur) + abs(h2s - h2_cur))
        return c

    lo_s = sp_lo if sp_lo > 0.03 else 0.03
    hi_s = sp_hi if sp_hi < 1.45 else 1.45
    if hi_s <= lo_s:
        return {"diagnosis": "degenerate setpoint limits",
                "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur}}

    best = None
    best_cost = None
    N = 350
    for i in range(N + 1):
        h1s = lo_s + (hi_s - lo_s) * (i / float(N))
        h2s = h2_for_Q(h1s)
        if h2s is None:
            continue
        if h2s < lo_s or h2s > hi_s:
            continue
        c = cost(h1s, h2s)
        if best_cost is None or c < best_cost:
            best_cost = c
            best = (h1s, h2s)

    if lo_s <= h1_cur <= hi_s and lo_s <= h2_cur <= hi_s:
        c = cost(h1_cur, h2_cur)
        if best_cost is None or c < best_cost:
            best_cost = c
            best = (h1_cur, h2_cur)

    if best is None:
        nomQ = F1f(0.30) + F2f(0.35)
        if nomQ > 1e-9:
            sc = (Q_tgt / nomQ) ** 2
        else:
            sc = 1.0
        h1o = 0.30 * sc
        h2o = 0.35 * sc
        if h1o < sp_lo:
            h1o = sp_lo
        if h1o > sp_hi:
            h1o = sp_hi
        if h2o < sp_lo:
            h2o = sp_lo
        if h2o > sp_hi:
            h2o = sp_hi
        best = (h1o, h2o)

    h1o = best[0]
    h2o = best[1]
    if h1o < sp_lo:
        h1o = sp_lo
    if h1o > sp_hi:
        h1o = sp_hi
    if h2o < sp_lo:
        h2o = sp_lo
    if h2o > sp_hi:
        h2o = sp_hi

    diag = ("Q_tgt=%.2f L/s d=[%.2f,%.2f] L/s u=[%.1e,%.1e] sp=(%.3f,%.3f)"
            % (Q_tgt * 1000.0, d1 * 1000.0, d2 * 1000.0, u1, u2, h1o, h2o))
    return {"diagnosis": diag,
            "adjusted_setpoints": {"h1": float(h1o), "h2": float(h2o)}}
