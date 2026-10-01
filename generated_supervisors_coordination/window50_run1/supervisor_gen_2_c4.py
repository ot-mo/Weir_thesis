def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1n = 0.00085
    k2n = 0.00095
    c = math.sqrt(2.0 * 9.81)
    QNOM = 16.35286638873749
    S = 4.0 / 3.0

    try:
        h1a = float(active_setpoints["h1"])
        h2a = float(active_setpoints["h2"])
    except Exception:
        h1a = 0.30
        h2a = 0.35
    fb = {"diagnosis": "hold setpoints", "adjusted_setpoints": {"h1": h1a, "h2": h2a}}

    try:
        Q_t = float(objectives["production_target"])
        band = objectives["h2_band"]
        bh2lo = float(band[0])
        bh2hi = float(band[1])
        ulim = float(objectives["upper_level_limit"])
        slim = objectives["setpoint_limits"]
        splo = float(slim[0])
        sphi = float(slim[1])
        n = len(telemetry_window)
        if n < 5 or Q_t <= 0.0:
            return fb
        M = 20
        if M > n:
            M = n
        tail = telemetry_window[n - M:]

        def fit(key):
            vals = []
            for row in tail:
                vals.append(float(row[key]))
            mm = len(vals)
            mt = (mm - 1) * 0.5
            num = 0.0
            den = 0.0
            s = 0.0
            for i in range(mm):
                d = i - mt
                num += d * vals[i]
                den += d * d
                s += vals[i]
            if den <= 0.0:
                return vals[-1], 0.0
            sl = num / den
            return s / mm + sl * (mm - 1 - mt), sl

        h1, sh1 = fit("h1")
        h2, sh2 = fit("h2")
        h3, sh3 = fit("h3")
        h4, sh4 = fit("h4")
        v1, sv1 = fit("v1")
        v2, sv2 = fit("v2")
    except Exception:
        return fb

    if h1 < 0.0:
        h1 = 0.0
    if h2 < 0.0:
        h2 = 0.0
    if h3 < 0.0:
        h3 = 0.0
    if h4 < 0.0:
        h4 = 0.0

    sc = (Q_t / QNOM) ** 2
    if sc < 0.01:
        sc = 0.01
    if sc > 8.0:
        sc = 8.0
    h1n = 0.30 * sc
    h2n = 0.35 * sc

    h1_lo = 0.02
    if splo > h1_lo:
        h1_lo = splo
    h1_hi = 1.5
    if sphi < h1_hi:
        h1_hi = sphi
    h2_lo = 0.02
    if splo > h2_lo:
        h2_lo = splo
    if bh2lo > h2_lo:
        h2_lo = bh2lo
    h2_hi = 1.5
    if sphi < h2_hi:
        h2_hi = sphi
    if bh2hi < h2_hi:
        h2_hi = bh2hi
    if h1_hi - h1_lo > 0.05:
        h1_lo = h1_lo + 0.004
        h1_hi = h1_hi - 0.004
    if h2_hi - h2_lo > 0.05:
        h2_lo = h2_lo + 0.004
        h2_hi = h2_hi - 0.004
    if h1_lo > h1_hi:
        h1_lo = 0.5 * (h1_lo + h1_hi)
        h1_hi = h1_lo
    if h2_lo > h2_hi:
        h2_lo = 0.5 * (h2_lo + h2_hi)
        h2_hi = h2_lo

    if h1n < h1_lo:
        h1n = h1_lo
    if h1n > h1_hi:
        h1n = h1_hi
    if h2n < h2_lo:
        h2n = h2_lo
    if h2n > h2_hi:
        h2n = h2_hi

    Q1n = 1000.0 * a1 * c * math.sqrt(h1n)
    Q2n = 1000.0 * a2 * c * math.sqrt(h2n)

    hard_lo = Q1n - 1000.0 * a1 * c * math.sqrt(h1_hi)
    tt = 1000.0 * a2 * c * math.sqrt(h2_lo) - Q2n
    if tt > hard_lo:
        hard_lo = tt
    hard_hi = Q1n - 1000.0 * a1 * c * math.sqrt(h1_lo)
    tt = 1000.0 * a2 * c * math.sqrt(h2_hi) - Q2n
    if tt < hard_hi:
        hard_hi = tt
    if hard_lo < -3.0:
        hard_lo = -3.0
    if hard_hi > 3.0:
        hard_hi = 3.0
    if hard_lo > hard_hi:
        mid = 0.5 * (hard_lo + hard_hi)
        hard_lo = mid
        hard_hi = mid

    inf3 = 1000.0 * a3 * c * math.sqrt(h3)
    inf4 = 1000.0 * a4 * c * math.sqrt(h4)
    I3 = inf3 + 1000.0 * sh3
    I4 = inf4 + 1000.0 * sh4
    if I3 < 0.0:
        I3 = 0.0
    if I4 < 0.0:
        I4 = 0.0

    k2e = k2n
    if v2 > 0.5:
        ee = I3 * 1.0e-3 / (0.8 * v2)
        if ee > 0.45 * k2n and ee < 1.6 * k2n:
            k2e = ee
    k1e = k1n
    if v1 > 0.5:
        ee = I4 * 1.0e-3 / (0.8 * v1)
        if ee > 0.45 * k1n and ee < 1.6 * k1n:
            k1e = ee

    d1 = 1000.0 * (sh1 + a1 * c * math.sqrt(h1)) - inf3 - 0.25 * I4
    d2 = 1000.0 * (sh2 + a2 * c * math.sqrt(h2)) - inf4 - 0.25 * I3
    if d1 > 5.0:
        d1 = 5.0
    if d1 < -5.0:
        d1 = -5.0
    if d2 > 5.0:
        d2 = 5.0
    if d2 < -5.0:
        d2 = -5.0

    i3_0 = (Q1n - d1 - 0.25 * (Q2n - d2)) / 0.9375
    i4_0 = (Q2n - d2 - 0.25 * (Q1n - d1)) / 0.9375
    if i3_0 < 0.0:
        i3_0 = 0.0
    if i4_0 < 0.0:
        i4_0 = 0.0

    h3t = ulim - 0.05
    if 0.93 * ulim < h3t:
        h3t = 0.93 * ulim
    if h3t < 0.05:
        h3t = 0.05
    I3t = 1000.0 * a3 * c * math.sqrt(h3t)
    I4t = 1000.0 * a4 * c * math.sqrt(h3t)

    vcap = 11.2
    I3v = 800.0 * k2e * vcap
    I4v = 800.0 * k1e * vcap

    lo = hard_lo
    hi = hard_hi
    tt = (i3_0 - I3t) / S
    if tt > lo:
        lo = tt
    tt = (i3_0 - I3v) / S
    if tt > lo:
        lo = tt
    tt = (I4t - i4_0) / S
    if tt < hi:
        hi = tt
    tt = (I4v - i4_0) / S
    if tt < hi:
        hi = tt

    g3 = 0.75 * 1000.0 * a3 * c / (2.0 * math.sqrt(max(h3, 0.06)))
    e3 = h3 + sh3 * 10.0 - h3t
    if e3 > 0.0:
        tt = g3 * e3
        if tt > lo:
            lo = tt
    g4 = 0.75 * 1000.0 * a4 * c / (2.0 * math.sqrt(max(h4, 0.06)))
    e4 = h4 + sh4 * 10.0 - h3t
    if e4 > 0.0:
        tt = -g4 * e4
        if tt < hi:
            hi = tt

    if lo > hi:
        mid = 0.5 * (lo + hi)
        if mid < hard_lo:
            mid = hard_lo
        if mid > hard_hi:
            mid = hard_hi
        lo = mid
        hi = mid
    if lo < hard_lo:
        lo = hard_lo
    if hi > hard_hi:
        hi = hard_hi

    Q1a = 1000.0 * a1 * c * math.sqrt(max(h1a, 0.0001))
    Q2a = 1000.0 * a2 * c * math.sqrt(max(h2a, 0.0001))
    dprev = 0.5 * ((Q1n - Q1a) + (Q2a - Q2n))
    if dprev > 3.0:
        dprev = 3.0
    if dprev < -3.0:
        dprev = -3.0

    if dprev < lo:
        want = lo
    elif dprev > hi:
        want = hi
    else:
        want = dprev * 0.999
        if abs(want) < 0.01:
            want = 0.0

    step = want - dprev
    if step > 0.20:
        step = 0.20
    if step < -0.20:
        step = -0.20
    dnew = dprev + step
    if abs(dnew) < 0.01:
        dnew = 0.0
    if dnew > 3.0:
        dnew = 3.0
    if dnew < -3.0:
        dnew = -3.0

    Q1s = Q1n - dnew
    Q2s = Q2n + dnew
    if Q1s < 0.05:
        Q1s = 0.05
    if Q2s < 0.05:
        Q2s = 0.05
    h1s = (Q1s / (1000.0 * a1 * c)) ** 2
    h2s = (Q2s / (1000.0 * a2 * c)) ** 2
    if h1s < h1_lo:
        h1s = h1_lo
    if h1s > h1_hi:
        h1s = h1_hi
    if h2s < h2_lo:
        h2s = h2_lo
    if h2s > h2_hi:
        h2s = h2_hi

    diag = "d=%+.2f i3=%.2f/%.2f i4=%.2f/%.2f v1=%.1f v2=%.1f" % (dnew, i3_0, I3v, i4_0, I4v, v1, v2)
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1s, "h2": h2s}}
