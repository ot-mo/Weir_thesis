def supervise(telemetry_window, active_setpoints, objectives):
    sq2g = 4.42944691807002
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    gam1 = 0.20
    gam2 = 0.20
    NOM_RATIO = 0.51927
    p1_nom = (1.0 - gam1) * k1
    p2_nom = (1.0 - gam2) * k2

    def fl(a, h):
        if h <= 0.0:
            return 0.0
        return a * sq2g * math.sqrt(h)

    n = len(telemetry_window)
    if n < 10:
        return {"diagnosis": "too few samples, holding setpoints",
                "adjusted_setpoints": {"h1": float(active_setpoints["h1"]),
                                       "h2": float(active_setpoints["h2"])}}

    m = 30
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
        s1 += r["h1"]
        s2 += r["h2"]
        s3 += r["h3"]
        s4 += r["h4"]
        sv1 += r["v1"]
        sv2 += r["v2"]
    h1m = s1 / m
    h2m = s2 / m
    h3m = s3 / m
    h4m = s4 / m
    v1m = sv1 / m
    v2m = sv2 / m

    m2 = 10
    if m2 > m:
        m2 = m
    seg = win[m - m2:m]
    dt = seg[m2 - 1]["time"] - seg[0]["time"]
    if dt <= 0.0:
        dt = 1.0
    slh3 = (seg[m2 - 1]["h3"] - seg[0]["h3"]) / dt
    slh4 = (seg[m2 - 1]["h4"] - seg[0]["h4"]) / dt

    Q = objectives["production_target"] / 1000.0
    if Q <= 0.0:
        Q = 0.0163529

    uplim = objectives["upper_level_limit"]
    h3t = uplim - 0.10
    if h3t < 0.15:
        h3t = 0.15
    h4t = h3t

    Tpred = 15.0
    h3_eff = h3m + max(0.0, min(0.12, slh3 * Tpred))
    h4_eff = h4m + max(0.0, min(0.12, slh4 * Tpred))

    v2sat = 11.7
    v1sat = 11.7

    if h3_eff > 0.05 and v2m > 0.2:
        v2max = v2m * math.sqrt(h3t / h3_eff)
    else:
        v2max = 12.0
    if v2max > v2sat:
        v2max = v2sat
    if v2max < 1.0:
        v2max = 1.0

    if h4_eff > 0.05 and v1m > 0.2:
        v1max = v1m * math.sqrt(h4t / h4_eff)
    else:
        v1max = 12.0
    if v1max > v1sat:
        v1max = v1sat
    if v1max < 1.0:
        v1max = 1.0

    dv2 = v2m - v2max
    if dv2 < 0.0:
        dv2 = 0.0
    dv1 = v1m - v1max
    if dv1 < 0.0:
        dv1 = 0.0

    if v2m > 0.5 and h3m > 0.01:
        gf2 = (fl(a3, h3m) / v2m) / p2_nom
        if gf2 < 0.6:
            gf2 = 0.6
        if gf2 > 1.5:
            gf2 = 1.5
    else:
        gf2 = 1.0
    if v1m > 0.5 and h4m > 0.01:
        gf1 = (fl(a4, h4m) / v1m) / p1_nom
        if gf1 < 0.6:
            gf1 = 0.6
        if gf1 > 1.5:
            gf1 = 1.5
    else:
        gf1 = 1.0

    k2e = k2 * gf2
    k1e = k1 * gf1

    F1 = NOM_RATIO * Q
    alpha = 0.7
    F1 -= alpha * 0.6 * k2e * dv2
    F1 += alpha * 0.6 * k1e * dv1

    h2lo, h2hi = objectives["h2_band"]
    Kfb2 = 0.02
    if h2m > h2hi - 0.01:
        F1 += Kfb2 * (h2m - (h2hi - 0.01))
    if h2m < h2lo + 0.01:
        F1 -= Kfb2 * ((h2lo + 0.01) - h2m)

    mband = 0.01
    band_lo = Q - fl(a2, h2hi - mband)
    band_hi = Q - fl(a2, h2lo + mband)
    if band_lo > band_hi:
        tmp = band_lo
        band_lo = band_hi
        band_hi = tmp
    if F1 < band_lo:
        F1 = band_lo
    if F1 > band_hi:
        F1 = band_hi

    sp_lo, sp_hi = objectives["setpoint_limits"]
    if F1 < fl(a1, sp_lo):
        F1 = fl(a1, sp_lo)
    if F1 > fl(a1, sp_hi):
        F1 = fl(a1, sp_hi)
    if F1 < fl(a1, 0.02):
        F1 = fl(a1, 0.02)
    if F1 > fl(a1, 1.5):
        F1 = fl(a1, 1.5)

    F2 = Q - F1
    if F2 < fl(a2, 0.02):
        F2 = fl(a2, 0.02)
    if F2 > fl(a2, 1.5):
        F2 = fl(a2, 1.5)
    F1 = Q - F2

    if F1 > 1e-8:
        h1_sp = (F1 / (sq2g * a1)) ** 2
    else:
        h1_sp = 0.0
    if F2 > 1e-8:
        h2_sp = (F2 / (sq2g * a2)) ** 2
    else:
        h2_sp = 0.0

    h1_sp = min(sp_hi, max(sp_lo, h1_sp))
    h2_sp = min(sp_hi, max(sp_lo, h2_sp))

    ah1 = active_setpoints["h1"]
    ah2 = active_setpoints["h2"]

    if abs(h1_sp - ah1) < 0.002 and abs(h2_sp - ah2) < 0.002:
        h1_sp = ah1
        h2_sp = ah2
    else:
        maxstep = 0.03
        if h1_sp > ah1 + maxstep:
            h1_sp = ah1 + maxstep
        if h1_sp < ah1 - maxstep:
            h1_sp = ah1 - maxstep
        if h2_sp > ah2 + maxstep:
            h2_sp = ah2 + maxstep
        if h2_sp < ah2 - maxstep:
            h2_sp = ah2 - maxstep
        h1_sp = min(sp_hi, max(sp_lo, h1_sp))
        h2_sp = min(sp_hi, max(sp_lo, h2_sp))

    diag = ("h3eff=" + str(round(h3_eff, 3)) + " v2max=" + str(round(v2max, 2)) +
            " dv2=" + str(round(dv2, 2)) + " h4eff=" + str(round(h4_eff, 3)) +
            " v1max=" + str(round(v1max, 2)) + " dv1=" + str(round(dv1, 2)) +
            " -> sp=" + str(round(h1_sp, 3)) + "," + str(round(h2_sp, 3)))
    return {"diagnosis": diag,
            "adjusted_setpoints": {"h1": float(h1_sp), "h2": float(h2_sp)}}