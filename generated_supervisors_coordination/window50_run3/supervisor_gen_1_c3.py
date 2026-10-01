def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    rt2g = math.sqrt(2.0 * g)
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1n = 0.00085
    k2n = 0.00095
    A = 0.20 * k1n
    B0 = 0.80 * k2n
    C0 = 0.80 * k1n
    D = 0.20 * k2n
    Q_nom = 0.016352866
    u1_nom = a1 * rt2g * math.sqrt(0.30)

    ah1 = active_setpoints["h1"]
    ah2 = active_setpoints["h2"]
    n = len(telemetry_window)
    if n < 3:
        return {"diagnosis": "insufficient telemetry, holding setpoints",
                "adjusted_setpoints": {"h1": ah1, "h2": ah2}}

    def slope(key, m):
        if m > n:
            m = n
        if m < 3:
            return 0.0
        seg = telemetry_window[-m:]
        tbar = 0.0
        ybar = 0.0
        for s in seg:
            tbar += s["time"]
            ybar += s[key]
        tbar = tbar / m
        ybar = ybar / m
        num = 0.0
        den = 0.0
        for s in seg:
            dt = s["time"] - tbar
            num += dt * (s[key] - ybar)
            den += dt * dt
        if den <= 0.0:
            return 0.0
        return num / den

    last = telemetry_window[-1]
    h1 = last["h1"]
    h2 = last["h2"]
    h3 = last["h3"]
    h4 = last["h4"]
    v1 = last["v1"]
    v2 = last["v2"]

    dh1 = slope("h1", 15)
    dh2 = slope("h2", 15)
    dh3 = slope("h3", 15)
    dh4 = slope("h4", 15)

    u1 = a1 * rt2g * math.sqrt(max(h1, 0.0))
    u2 = a2 * rt2g * math.sqrt(max(h2, 0.0))
    f3 = a3 * rt2g * math.sqrt(max(h3, 0.0))
    f4 = a4 * rt2g * math.sqrt(max(h4, 0.0))

    Beff = B0
    if v2 > 0.5:
        Beff = (dh3 + f3) / v2
    if Beff < 0.00030:
        Beff = 0.00030
    if Beff > 0.00130:
        Beff = 0.00130
    Ceff = C0
    if v1 > 0.5:
        Ceff = (dh4 + f4) / v1
    if Ceff < 0.00030:
        Ceff = 0.00030
    if Ceff > 0.00130:
        Ceff = 0.00130

    m1 = dh1 + u1 - A * v1 - f3
    m2 = dh2 + u2 - D * v2 - f4
    if m1 < -0.006:
        m1 = -0.006
    if m1 > 0.006:
        m1 = 0.006
    if m2 < -0.006:
        m2 = -0.006
    if m2 > 0.006:
        m2 = 0.006

    det = A * D - Beff * Ceff

    Q = objectives["production_target"] / 1000.0
    h2lo = objectives["h2_band"][0]
    h2hi = objectives["h2_band"][1]
    ulim = objectives["upper_level_limit"]
    splo = objectives["setpoint_limits"][0]
    sphi = objectives["setpoint_limits"][1]

    u1_free = u1_nom * (Q / Q_nom)

    h3_t = ulim - 0.05
    if h3_t < 0.05:
        h3_t = 0.05
    h4_t = ulim - 0.05
    if h4_t < 0.05:
        h4_t = 0.05

    v2_max = 12.0
    if Beff > 1e-9:
        v2_max = a3 * rt2g * math.sqrt(h3_t) / Beff
    if v2_max > 12.0:
        v2_max = 12.0
    v1_max = 12.0
    if Ceff > 1e-9:
        v1_max = a4 * rt2g * math.sqrt(h4_t) / Ceff
    if v1_max > 12.0:
        v1_max = 12.0

    u2max_band = a2 * rt2g * math.sqrt(max(h2hi - 0.02, 1e-6))
    u2min_band = a2 * rt2g * math.sqrt(max(h2lo + 0.02, 1e-6))
    lo = Q - u2max_band
    hi = Q - u2min_band
    if lo < 0.0:
        lo = 0.0
    if hi > Q:
        hi = Q

    if abs(det) > 1e-12:
        u1_v2 = (A * Q - A * m2 + Ceff * m1 - v2_max * det) / (A + Ceff)
        u1_v1 = (v1_max * det + D * m1 + Beff * Q - Beff * m2) / (D + Beff)
        if det < 0.0:
            if u1_v2 < hi:
                hi = u1_v2
            if u1_v1 > lo:
                lo = u1_v1
        else:
            if u1_v2 > lo:
                lo = u1_v2
            if u1_v1 < hi:
                hi = u1_v1

    conflict = False
    if hi < lo:
        conflict = True
        u1_t = lo
    else:
        u1_t = u1_free
        if u1_t < lo:
            u1_t = lo
        if u1_t > hi:
            u1_t = hi

    if u1_t < 0.0:
        u1_t = 0.0
    if u1_t > Q:
        u1_t = Q

    u1_a = a1 * rt2g * math.sqrt(max(ah1, 0.0))
    if u1_t > u1_a + 0.0006:
        u1_t = u1_a + 0.0006
    elif u1_t < u1_a - 0.0006:
        u1_t = u1_a - 0.0006
    if abs(u1_t - u1_a) < 2.5e-5:
        u1_t = u1_a

    u2_t = Q - u1_t
    if u2_t < 1e-6:
        u2_t = 1e-6

    h1_t = (u1_t / (a1 * rt2g)) ** 2
    h2_t = (u2_t / (a2 * rt2g)) ** 2

    if h1_t < splo:
        h1_t = splo
    if h1_t > sphi:
        h1_t = sphi
    if h2_t < splo:
        h2_t = splo
    if h2_t > sphi:
        h2_t = sphi

    diag = "Qsp=%.2fL/s d1=%.2f d2=%.2fL/s v2max=%.1f h1 %.3f->%.3f h2 %.3f->%.3f" % (
        Q * 1000.0, m1 * 1000.0, m2 * 1000.0, v2_max, ah1, h1_t, ah2, h2_t)
    if conflict:
        diag = "constraints conflict, h2 band prioritised; " + diag

    return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1_t, "h2": h2_t}}
