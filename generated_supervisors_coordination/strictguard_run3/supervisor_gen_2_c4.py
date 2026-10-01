def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    sq2g = math.sqrt(2.0 * g)
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    gam1 = 0.20
    gam2 = 0.20
    c1 = (1.0 - gam1) * k1
    c2 = (1.0 - gam2) * k2
    ep1 = gam1 * k1
    ep2 = gam2 * k2
    A1 = a1 * sq2g
    A2 = a2 * sq2g
    A3 = a3 * sq2g
    A4 = a4 * sq2g

    def ssqrt(x):
        if x > 0.0:
            return math.sqrt(x)
        return 0.0

    try:
        Q_target = float(objectives["production_target"])
        lim_lo = float(objectives["setpoint_limits"][0])
        lim_hi = float(objectives["setpoint_limits"][1])
        band_lo = float(objectives["h2_band"][0])
        band_hi = float(objectives["h2_band"][1])
        ulim = float(objectives["upper_level_limit"])
        sp1 = float(active_setpoints["h1"])
        sp2 = float(active_setpoints["h2"])
    except (TypeError, ValueError, KeyError, IndexError, AttributeError):
        return {"diagnosis": "bad arguments; holding nominal",
                "adjusted_setpoints": {"h1": 0.30, "h2": 0.35}}

    Qm = Q_target / 1000.0
    safe_lo = 0.02
    safe_hi = 1.5

    n = len(telemetry_window) if telemetry_window is not None else 0
    if n < 2:
        return {"diagnosis": "insufficient telemetry",
                "adjusted_setpoints": {"h1": sp1, "h2": sp2}}

    last = telemetry_window[n - 1]
    h1m = float(last["h1"])
    h2m = float(last["h2"])
    v1m = float(last["v1"])
    v2m = float(last["v2"])

    W = 12
    if W > n - 1:
        W = n - 1
    if W < 1:
        W = 1
    i0 = n - 1 - W
    s1 = 0.0; s3 = 0.0; sv1 = 0.0
    s2 = 0.0; s4 = 0.0; sv2 = 0.0
    for i in range(i0, n - 1):
        rec = telemetry_window[i]
        s1 += A1 * ssqrt(float(rec["h1"]))
        s3 += A3 * ssqrt(float(rec["h3"]))
        sv1 += ep1 * float(rec["v1"])
        s2 += A2 * ssqrt(float(rec["h2"]))
        s4 += A4 * ssqrt(float(rec["h4"]))
        sv2 += ep2 * float(rec["v2"])
    h1_0 = float(telemetry_window[i0]["h1"])
    h2_0 = float(telemetry_window[i0]["h2"])
    d1 = ((h1m - h1_0) + s1 - s3 - sv1) / float(W)
    d2 = ((h2m - h2_0) + s2 - s4 - sv2) / float(W)
    dmax = 0.010
    if d1 > dmax: d1 = dmax
    if d1 < -dmax: d1 = -dmax
    if d2 > dmax: d2 = dmax
    if d2 < -dmax: d2 = -dmax

    det = c1 * c2 - ep1 * ep2

    def predict(h1c, h2c):
        r1 = A1 * ssqrt(h1c) - d1
        r2 = A2 * ssqrt(h2c) - d2
        v1c = (c2 * r2 - ep2 * r1) / det
        v2c = (c1 * r1 - ep1 * r2) / det
        h3c = (c2 * v2c / A3) ** 2
        h4c = (c1 * v1c / A4) ** 2
        return v1c, v2c, h3c, h4c

    v1_cur, v2_cur, _, _ = predict(sp1, sp2)
    f1 = 1.0
    f2 = 1.0
    if v1_cur > 0.3:
        f1 = v1m / v1_cur
        if f1 < 0.5: f1 = 0.5
        if f1 > 2.0: f1 = 2.0
    if v2_cur > 0.3:
        f2 = v2m / v2_cur
        if f2 < 0.5: f2 = 0.5
        if f2 > 2.0: f2 = 2.0

    W_TRAVEL = 100.0
    W_Q = 1.0e7
    W_UL = 1200.0
    W_BAND = 1000.0
    W_SAT = 800.0
    ulim_soft = ulim - 0.02
    blo = band_lo + 0.005
    bhi = band_hi - 0.005
    if bhi < blo:
        bhi = (band_lo + band_hi) * 0.5
        blo = bhi

    def cost_of(h1c, h2c):
        c = W_TRAVEL * (abs(h1c - sp1) + abs(h2c - sp2))
        q = A1 * ssqrt(h1c) + A2 * ssqrt(h2c)
        c += W_Q * abs(q - Qm)
        v1c, v2c, h3c, h4c = predict(h1c, h2c)
        if h3c > ulim_soft:
            c += W_UL * (h3c - ulim_soft)
        if h4c > ulim_soft:
            c += W_UL * (h4c - ulim_soft)
        if h2c < blo:
            c += W_BAND * (blo - h2c)
        elif h2c > bhi:
            c += W_BAND * (h2c - bhi)
        cv1 = v1c * f1
        cv2 = v2c * f2
        if cv1 > 11.5:
            c += W_SAT * (cv1 - 11.5)
        elif cv1 < 1.5:
            c += W_SAT * (1.5 - cv1)
        if cv2 > 11.5:
            c += W_SAT * (cv2 - 11.5)
        elif cv2 < 1.5:
            c += W_SAT * (1.5 - cv2)
        return c

    lo_sp = max(safe_lo, lim_lo)
    hi_sp = min(safe_hi, lim_hi)

    h2_lo_eff = max(safe_lo, lim_lo)
    h2_hi_eff = min(safe_hi, lim_hi)
    q2_lo = A2 * math.sqrt(h2_lo_eff)
    q2_hi = A2 * math.sqrt(h2_hi_eff)
    q1_hi = Qm - q2_lo
    q1_lo = Qm - q2_hi
    if q1_lo < 0.0:
        q1_lo = 0.0
    if q1_hi < 0.0:
        q1_hi = 0.0
    h1_lo = max(lo_sp, (q1_lo / A1) ** 2)
    h1_hi = min(hi_sp, (q1_hi / A1) ** 2)
    if h1_hi <= h1_lo:
        h1_lo = lo_sp
        h1_hi = hi_sp

    best_h1 = sp1
    best_h2 = sp2
    best_c = cost_of(sp1, sp2)

    Nc = 61
    if h1_hi > h1_lo:
        dstep = (h1_hi - h1_lo) / float(Nc - 1)
        for i in range(Nc):
            h1c = h1_lo + dstep * i
            q1c = A1 * ssqrt(h1c)
            q2c = Qm - q1c
            if q2c <= 0.0:
                continue
            h2c = (q2c / A2) ** 2
            if h2c < safe_lo or h2c > safe_hi:
                continue
            cc = cost_of(h1c, h2c)
            if cc < best_c:
                best_c = cc
                best_h1 = h1c
                best_h2 = h2c

    for span, npts in ((0.05, 21), (0.01, 21), (0.002, 11)):
        c0 = best_h1
        for i in range(npts):
            h1c = c0 - span + (2.0 * span) * i / float(npts - 1)
            if h1c < lo_sp or h1c > hi_sp:
                continue
            q1c = A1 * ssqrt(h1c)
            q2c = Qm - q1c
            if q2c <= 0.0:
                continue
            h2c = (q2c / A2) ** 2
            if h2c < safe_lo or h2c > safe_hi:
                continue
            cc = cost_of(h1c, h2c)
            if cc < best_c:
                best_c = cc
                best_h1 = h1c
                best_h2 = h2c

    out1 = best_h1
    out2 = best_h2
    if out1 < lo_sp: out1 = lo_sp
    if out1 > hi_sp: out1 = hi_sp
    if out2 < safe_lo: out2 = safe_lo
    if out2 > safe_hi: out2 = safe_hi
    if out2 < lim_lo: out2 = lim_lo
    if out2 > lim_hi: out2 = lim_hi

    diag = "SS supervisor: d1=%.4f d2=%.4f; sp=(%.4f, %.4f)" % (d1, d2, out1, out2)
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": out1, "h2": out2}}
