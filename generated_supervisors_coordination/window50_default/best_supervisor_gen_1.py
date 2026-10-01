def supervise(telemetry_window, active_setpoints, objectives):
    sq2g = 4.42944691807002  # sqrt(2*9.81)
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    gam1 = 0.20
    gam2 = 0.20
    NOM_RATIO = 0.51927  # F1/Q at the design operating point

    def fl(a, h):
        if h <= 0.0:
            return 0.0
        return a * sq2g * math.sqrt(h)

    n = len(telemetry_window)
    if n < 5:
        return {"diagnosis": "too few samples, holding setpoints",
                "adjusted_setpoints": {"h1": float(active_setpoints["h1"]),
                                       "h2": float(active_setpoints["h2"])}}

    m = 20
    if n < m:
        m = n
    win = telemetry_window[n - m:n]

    s1 = 0.0
    s2 = 0.0
    s3 = 0.0
    s4 = 0.0
    sv1 = 0.0
    sv2 = 0.0
    for r in win:
        s1 = s1 + r["h1"]
        s2 = s2 + r["h2"]
        s3 = s3 + r["h3"]
        s4 = s4 + r["h4"]
        sv1 = sv1 + r["v1"]
        sv2 = sv2 + r["v2"]
    h1m = s1 / m
    h2m = s2 / m
    h3m = s3 / m
    h4m = s4 / m
    v1m = sv1 / m
    v2m = sv2 / m

    dt = win[m - 1]["time"] - win[0]["time"]
    if dt <= 0.0:
        dt = 1.0
    slh1 = (win[m - 1]["h1"] - win[0]["h1"]) / dt
    slh2 = (win[m - 1]["h2"] - win[0]["h2"]) / dt

    # effective additive feed disturbances from tank1 / tank2 balances
    r1 = fl(a1, h1m) - fl(a3, h3m) - gam1 * k1 * v1m
    r2 = fl(a2, h2m) - fl(a4, h4m) - gam2 * k2 * v2m
    d1 = r1 + slh1
    d2 = r2 + slh2

    Q = objectives["production_target"] / 1000.0
    if Q <= 0.0:
        Q = 0.0163529

    uplim = objectives["upper_level_limit"]
    h3t = uplim - 0.05
    if h3t < 0.10:
        h3t = 0.10
    h4t = h3t

    bmax = fl(a3, h3t) / (1.0 - gam2)   # upper bound on k2*v2 (h3)
    amax = fl(a4, h4t) / (1.0 - gam1)   # upper bound on k1*v1 (h4)

    Fu_hi = 0.6 * bmax + 0.2 * Q + 0.8 * d1 - 0.2 * d2
    Fu_lo = 0.8 * Q - 0.8 * d2 + 0.2 * d1 - 0.6 * amax

    h2lo, h2hi = objectives["h2_band"]
    Fb_lo = Q - fl(a2, h2hi)
    Fb_hi = Q - fl(a2, h2lo)

    sp_lo, sp_hi = objectives["setpoint_limits"]
    lo_all = max(Fu_lo, Q - fl(a2, sp_hi), fl(a1, sp_lo))
    hi_all = min(Fu_hi, Q - fl(a2, sp_lo), fl(a1, sp_hi))

    F1nom = NOM_RATIO * Q

    lo = max(lo_all, Fb_lo)
    hi = min(hi_all, Fb_hi)
    if lo <= hi:
        F1 = min(hi, max(lo, F1nom))
    elif lo_all <= hi_all:
        F1 = min(hi_all, max(lo_all, F1nom))
    else:
        F1 = 0.5 * (lo_all + hi_all)

    if F1 < 0.0:
        F1 = 0.0
    if F1 > Q:
        F1 = Q
    F2 = Q - F1

    x1 = F1 / (sq2g * a1)
    x2 = F2 / (sq2g * a2)
    h1_sp = x1 * x1
    h2_sp = x2 * x2
    if h1_sp < sp_lo:
        h1_sp = sp_lo
    if h1_sp > sp_hi:
        h1_sp = sp_hi
    if h2_sp < sp_lo:
        h2_sp = sp_lo
    if h2_sp > sp_hi:
        h2_sp = sp_hi

    ah1 = active_setpoints["h1"]
    ah2 = active_setpoints["h2"]
    if abs(h1_sp - ah1) < 0.003 and abs(h2_sp - ah2) < 0.003:
        h1_sp = ah1
        h2_sp = ah2

    diag = ("balance-est d1=" + str(round(d1, 5)) + " d2=" + str(round(d2, 5)) +
            " -> h1=" + str(round(h1_sp, 3)) + " h2=" + str(round(h2_sp, 3)))
    return {"diagnosis": diag,
            "adjusted_setpoints": {"h1": float(h1_sp), "h2": float(h2_sp)}}
