def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1 = 0.0035; a2 = 0.003; a3 = 0.002; a4 = 0.0025
    k1 = 0.00085; k2 = 0.00095
    A = 0.20 * k1
    B = 0.80 * k1
    C = 0.20 * k2
    D = 0.80 * k2

    try:
        Q_t = float(objectives["production_target"]) / 1000.0
        lim = objectives["setpoint_limits"]
        lo = float(lim[0]); hi = float(lim[1])
        band = objectives["h2_band"]
        b_lo = float(band[0]); b_hi = float(band[1])
        Ulim = float(objectives.get("upper_level_limit", 0.75))
        sp1 = float(active_setpoints["h1"]); sp2 = float(active_setpoints["h2"])
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return {"diagnosis": "bad arguments", "adjusted_setpoints": {"h1": 0.30, "h2": 0.35}}

    n = len(telemetry_window)
    if n == 0 or Q_t <= 0.0:
        return {"diagnosis": "no data; holding", "adjusted_setpoints": {"h1": sp1, "h2": sp2}}

    def root(x):
        if x < 0.0:
            x = 0.0
        return x ** 0.5

    # ---- estimate additive feed disturbances from whole window ----
    s1 = 0.0; s2 = 0.0; cnt = 0
    x0 = None
    for s in telemetry_window:
        try:
            hh1 = float(s["h1"]); hh2 = float(s["h2"])
            hh3 = float(s["h3"]); hh4 = float(s["h4"])
            vv1 = float(s["v1"]); vv2 = float(s["v2"])
            tt = float(s["time"])
        except (KeyError, TypeError, ValueError):
            continue
        p1 = a1 * root(2.0 * g * hh1)
        p2 = a2 * root(2.0 * g * hh2)
        s1 += p1 - A * vv1 - a3 * root(2.0 * g * hh3)
        s2 += p2 - C * vv2 - a4 * root(2.0 * g * hh4)
        cnt += 1
        if x0 is None:
            x0 = (tt, hh1, hh2)

    w = telemetry_window[n - 1]
    try:
        h1m = float(w["h1"]); h2m = float(w["h2"])
        v1m = float(w["v1"]); v2m = float(w["v2"])
        t1 = float(w["time"])
    except (KeyError, TypeError, ValueError):
        return {"diagnosis": "bad telemetry", "adjusted_setpoints": {"h1": sp1, "h2": sp2}}

    d1 = 0.0; d2 = 0.0
    if cnt > 0:
        d1 = s1 / cnt
        d2 = s2 / cnt
    if x0 is not None:
        dt = t1 - x0[0]
        if dt > 1.0:
            d1 += (h1m - x0[1]) / dt
            d2 += (h2m - x0[2]) / dt
    dcap = 0.004
    if d1 > dcap:
        d1 = dcap
    if d1 < -dcap:
        d1 = -dcap
    if d2 > dcap:
        d2 = dcap
    if d2 < -dcap:
        d2 = -dcap

    det = A * C - B * D
    if det > -1e-12:
        det = -0.6 * k1 * k2

    Pa1 = a1 * root(2.0 * g * sp1)
    Pa2 = a2 * root(2.0 * g * sp2)
    if Pa1 + Pa2 > 1e-9:
        r_act = Pa1 / (Pa1 + Pa2)
    else:
        r_act = 0.5

    Hsoft = 0.60
    W_SOFT = 200.0
    W_HARD = 400.0
    W_BAND = 300.0
    W_SAT = 250.0
    W_MOVE = 80.0
    W_SAFE = 5000.0

    def evaluate(r):
        P1 = r * Q_t
        P2 = Q_t - P1
        if P1 <= 0.0 or P2 <= 0.0:
            return None
        h1c = (P1 / a1) ** 2 / (2.0 * g)
        h2c = (P2 / a2) ** 2 / (2.0 * g)
        if h1c < lo or h1c > hi or h2c < lo or h2c > hi:
            return None
        v1 = (C * (P1 - d1) - D * (P2 - d2)) / det
        v2 = (A * (P2 - d2) - B * (P1 - d1)) / det
        if v1 <= 0.1 or v2 <= 0.1:
            return None
        h3c = (D * v2 / a3) ** 2 / (2.0 * g)
        h4c = (B * v1 / a4) ** 2 / (2.0 * g)
        cost = 0.0
        if h3c > Hsoft:
            cost += W_SOFT * (h3c - Hsoft)
        if h4c > Hsoft:
            cost += W_SOFT * (h4c - Hsoft)
        if h3c > Ulim:
            cost += W_HARD * (h3c - Ulim)
        if h4c > Ulim:
            cost += W_HARD * (h4c - Ulim)
        if v1 > 11.5:
            cost += W_SAT * (v1 - 11.5)
        if v2 > 11.5:
            cost += W_SAT * (v2 - 11.5)
        if h2c < b_lo:
            cost += W_BAND * (b_lo - h2c)
        if h2c > b_hi:
            cost += W_BAND * (h2c - b_hi)
        if h1c < 0.02:
            cost += W_SAFE * (0.02 - h1c)
        if h2c < 0.02:
            cost += W_SAFE * (0.02 - h2c)
        cost += W_MOVE * (abs(h1c - sp1) + abs(h2c - sp2))
        return (cost, h1c, h2c, v1, v2, h3c, h4c)

    res_stay = evaluate(r_act)
    best = None
    N = 80
    for i in range(N + 1):
        r = 0.02 + 0.96 * i / N
        res = evaluate(r)
        if res is None:
            continue
        if best is None or res[0] < best[0]:
            best = res

    if best is None:
        return {"diagnosis": "no feasible split; holding",
                "adjusted_setpoints": {"h1": sp1, "h2": sp2}}

    if res_stay is not None and best[0] > res_stay[0] - 0.6:
        r_new = r_act
        note = "hold"
    else:
        r_new = (a1 * root(2.0 * g * best[1])) / Q_t
        dr = 0.15
        if r_new > r_act + dr:
            r_new = r_act + dr
        if r_new < r_act - dr:
            r_new = r_act - dr
        note = "shift"
    if r_new < 0.02:
        r_new = 0.02
    if r_new > 0.98:
        r_new = 0.98

    P1f = r_new * Q_t
    P2f = Q_t - P1f
    h1f = (P1f / a1) ** 2 / (2.0 * g)
    h2f = (P2f / a2) ** 2 / (2.0 * g)
    if h1f < lo:
        h1f = lo
    if h1f > hi:
        h1f = hi
    if h2f < lo:
        h2f = lo
    if h2f > hi:
        h2f = hi

    diag = ("%s Q=%.2f L/s d=[%.4f,%.4f] pred v=[%.1f,%.1f] h3=%.2f h4=%.2f"
            % (note, Q_t * 1000.0, d1, d2, best[3], best[4], best[5], best[6]))
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1f, "h2": h2f}}