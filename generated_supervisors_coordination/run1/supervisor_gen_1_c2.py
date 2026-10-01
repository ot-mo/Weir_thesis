def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1n = 0.00085
    k2n = 0.00095
    gam1 = 0.2
    gam2 = 0.2

    try:
        Qt = float(objectives["production_target"]) / 1000.0
        h2lo = float(objectives["h2_band"][0])
        h2hi = float(objectives["h2_band"][1])
        hlim = float(objectives["upper_level_limit"])
        splo = float(objectives["setpoint_limits"][0])
        sphi = float(objectives["setpoint_limits"][1])
        h1a = float(active_setpoints["h1"])
        h2a = float(active_setpoints["h2"])
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return {"diagnosis": "invalid inputs, holding nominal", "adjusted_setpoints": {"h1": 0.30, "h2": 0.35}}

    n = len(telemetry_window)
    if n < 6:
        return {"diagnosis": "no telemetry", "adjusted_setpoints": {"h1": h1a, "h2": h2a}}

    last = telemetry_window[-1]
    try:
        h1 = float(last["h1"])
        h2 = float(last["h2"])
        h3 = float(last["h3"])
        h4 = float(last["h4"])
        v1 = float(last["v1"])
        v2 = float(last["v2"])
    except (KeyError, TypeError, ValueError, IndexError):
        return {"diagnosis": "bad sample", "adjusted_setpoints": {"h1": h1a, "h2": h2a}}

    j0 = n - 1 - 9
    if j0 < 0:
        j0 = 0
    t1 = last["time"]
    t0 = telemetry_window[j0]["time"]
    dt = t1 - t0
    if dt <= 0.5:
        dt = 1.0

    def d_of(key):
        return (last[key] - telemetry_window[j0][key]) / dt

    dh1 = d_of("h1")
    dh2 = d_of("h2")
    dh3 = d_of("h3")
    dh4 = d_of("h4")

    def r2g(hh):
        if hh < 0.0:
            hh = 0.0
        return math.sqrt(2.0 * g * hh)

    G1 = a1 * r2g(h1)
    G2 = a2 * r2g(h2)
    G3 = a3 * r2g(h3)
    G4 = a4 * r2g(h4)

    F1 = (G4 + dh4) / (1.0 - gam1)
    F2 = (G3 + dh3) / (1.0 - gam2)
    v1c = v1 if v1 > 0.5 else 0.5
    v2c = v2 if v2 > 0.5 else 0.5
    k1e = F1 / v1c
    k2e = F2 / v2c
    if k1e < 0.4 * k1n:
        k1e = 0.4 * k1n
    if k1e > 1.6 * k1n:
        k1e = 1.6 * k1n
    if k2e < 0.4 * k2n:
        k2e = 0.4 * k2n
    if k2e > 1.6 * k2n:
        k2e = 1.6 * k2n

    d1 = dh1 + G1 - G3 - gam1 * F1
    d2 = dh2 + G2 - G4 - gam2 * F2
    if d1 > 0.01:
        d1 = 0.01
    if d1 < -0.01:
        d1 = -0.01
    if d2 > 0.01:
        d2 = 0.01
    if d2 < -0.01:
        d2 = -0.01

    m11 = gam1 * k1e
    m12 = (1.0 - gam2) * k2e
    m21 = (1.0 - gam1) * k1e
    m22 = gam2 * k2e
    det = m11 * m22 - m12 * m21
    if det > -1e-12:
        det = -1e-12

    h3safe = hlim * 0.95
    if h3safe > hlim - 0.03:
        h3safe = hlim - 0.03
    if h3safe < 0.05:
        h3safe = 0.05
    v2cap = a3 * r2g(h3safe) / ((1.0 - gam2) * k2e)
    v1cap = a4 * r2g(h3safe) / ((1.0 - gam1) * k1e)
    if v2cap > 11.8:
        v2cap = 11.8
    if v1cap > 11.8:
        v1cap = 11.8
    if v2cap < 1.0:
        v2cap = 1.0
    if v1cap < 1.0:
        v1cap = 1.0

    h2lo_eff = h2lo + 0.002
    h2hi_eff = h2hi - 0.002
    if h2hi_eff < h2lo_eff:
        h2hi_eff = h2lo_eff

    def evaluate(Qtu):
        v2coef = -(m11 + m21) / det
        v2const = (m11 * (Qtu - d2) + m21 * d1) / det
        v1coef = (m22 + m12) / det
        v1const = (-m22 * d1 - m12 * Qtu + m12 * d2) / det
        lo = a1 * r2g(0.02)
        hi = a1 * r2g(1.5)
        b = a1 * r2g(splo)
        if b > lo:
            lo = b
        b = a1 * r2g(sphi)
        if b < hi:
            hi = b
        b = Qtu - a2 * r2g(h2hi_eff)
        if b > lo:
            lo = b
        b = Qtu - a2 * r2g(h2lo_eff)
        if b < hi:
            hi = b
        b = Qtu - a2 * r2g(sphi)
        if b > lo:
            lo = b
        b = Qtu - a2 * r2g(splo)
        if b < hi:
            hi = b
        if v2coef > 1e-9:
            b = (v2cap - v2const) / v2coef
            if b < hi:
                hi = b
        if v1coef < -1e-9:
            b = (v1cap - v1const) / v1coef
            if b > lo:
                lo = b
        return lo, hi

    lo, hi = evaluate(Qt)
    Qt_used = Qt
    if lo > hi:
        found = False
        for i in range(1, 31):
            s = 1.0 - 0.01 * i
            lu, hu = evaluate(Qt * s)
            if lu <= hu:
                Qt_used = Qt * s
                lo = lu
                hi = hu
                found = True
                break
        if not found:
            Qt_used = Qt * 0.7
            lo, hi = evaluate(Qt_used)
            if lo > hi:
                b = Qt_used - a2 * r2g(h2hi_eff)
                if b < 0.0025:
                    b = 0.0025
                hi2 = a1 * r2g(1.5)
                if b > hi2:
                    b = hi2
                lo = b
                hi = b

    def hq(x):
        return x * x / (2.0 * g)

    best = None
    Ns = 120
    span2 = hi - lo
    for i in range(Ns + 1):
        Q1 = lo + span2 * i / Ns
        Q2 = Qt_used - Q1
        if Q2 <= 1e-6:
            continue
        hh1 = hq(Q1 / a1)
        hh2 = hq(Q2 / a2)
        cost = abs(hh1 - h1a) + abs(hh2 - h2a)
        if best is None or cost < best[0]:
            best = (cost, hh1, hh2)

    if best is None:
        bh1 = h1a
        bh2 = h2a
    else:
        bh1 = best[1]
        bh2 = best[2]
        if abs(bh1 - h1a) + abs(bh2 - h2a) < 0.002:
            bh1 = h1a
            bh2 = h2a

    if bh1 < splo:
        bh1 = splo
    if bh1 > sphi:
        bh1 = sphi
    if bh2 < splo:
        bh2 = splo
    if bh2 > sphi:
        bh2 = sphi

    diag = ("model split: Qt=%.2f L/s k1e=%.5f k2e=%.5f d1=%.3f d2=%.3f L/s -> h1=%.3f h2=%.3f"
            % (Qt_used * 1000.0, k1e, k2e, d1 * 1000.0, d2 * 1000.0, bh1, bh2))
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": bh1, "h2": bh2}}
