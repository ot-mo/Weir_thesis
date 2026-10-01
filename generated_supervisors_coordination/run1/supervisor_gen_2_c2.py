def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    c = math.sqrt(2.0 * 9.81)
    C1 = 1000.0 * a1 * c
    C2 = 1000.0 * a2 * c
    C3 = 1000.0 * a3 * c
    C4 = 1000.0 * a4 * c
    QNOM = 16.35286638873749
    Q1N = C1 * math.sqrt(0.30)
    Q2N = C2 * math.sqrt(0.35)

    try:
        h1a = float(active_setpoints["h1"])
        h2a = float(active_setpoints["h2"])
    except Exception:
        h1a = 0.30
        h2a = 0.35
    fallback = {"diagnosis": "hold setpoints",
                "adjusted_setpoints": {"h1": h1a, "h2": h2a}}

    try:
        Q_t = float(objectives["production_target"])
        band = objectives["h2_band"]
        h2lo_b = float(band[0])
        h2hi_b = float(band[1])
        ulim = float(objectives["upper_level_limit"])
        lim = objectives["setpoint_limits"]
        splo = float(lim[0])
        sphi = float(lim[1])
        n = len(telemetry_window)
        if n < 6:
            return fallback
        m = 12
        if n < m:
            m = n
        tail = telemetry_window[n - m:]

        def fitv(key):
            vals = []
            for row in tail:
                vals.append(float(row[key]))
            j = len(vals)
            if j < 2:
                return vals[0], 0.0
            mt = (j - 1) * 0.5
            num = 0.0
            den = 0.0
            tot = 0.0
            for i in range(j):
                dd = i - mt
                num += dd * vals[i]
                den += dd * dd
                tot += vals[i]
            sl = num / den if den > 0.0 else 0.0
            return tot / j + sl * (j - 1 - mt), sl

        h1, sh1 = fitv("h1")
        h2, sh2 = fitv("h2")
        h3, sh3 = fitv("h3")
        h4, sh4 = fitv("h4")
        v1, sv1 = fitv("v1")
        v2, sv2 = fitv("v2")
    except Exception:
        return fallback

    if h1 < 0.0:
        h1 = 0.0
    if h2 < 0.0:
        h2 = 0.0
    if h3 < 0.0:
        h3 = 0.0
    if h4 < 0.0:
        h4 = 0.0

    s = Q_t / QNOM
    if s < 0.5:
        s = 0.5
    if s > 1.6:
        s = 1.6

    Q1a = C1 * math.sqrt(h1a) if h1a > 0.0 else 0.0
    Q2a = C2 * math.sqrt(h2a) if h2a > 0.0 else 0.0
    d0 = 0.5 * ((s * Q1N - Q1a) + (Q2a - s * Q2N))

    if v1 > 0.6:
        a1e = (C4 * math.sqrt(h4) + 1000.0 * sh4) / v1
    else:
        a1e = 0.68
    if v2 > 0.6:
        a2e = (C3 * math.sqrt(h3) + 1000.0 * sh3) / v2
    else:
        a2e = 0.76
    if a1e < 0.30:
        a1e = 0.30
    if a1e > 1.00:
        a1e = 1.00
    if a2e < 0.30:
        a2e = 0.30
    if a2e > 1.00:
        a2e = 1.00

    b1n = 0.25 * a1e
    b2n = 0.25 * a2e
    if v1 > 0.6:
        b1e = (C1 * math.sqrt(h1) + 1000.0 * sh1 - a2e * v2) / v1
    else:
        b1e = b1n
    if v2 > 0.6:
        b2e = (C2 * math.sqrt(h2) + 1000.0 * sh2 - a1e * v1) / v2
    else:
        b2e = b2n
    if b1e < 0.0:
        b1e = 0.0
    if b1e > 0.9:
        b1e = 0.9
    if b2e < 0.0:
        b2e = 0.0
    if b2e > 0.9:
        b2e = 0.9
    beta1 = 0.5 * b1n + 0.5 * b1e
    beta2 = 0.5 * b2n + 0.5 * b2e

    det = beta1 * beta2 - a1e * a2e
    if det > -0.08:
        a1e = 0.68
        a2e = 0.76
        beta1 = 0.17
        beta2 = 0.19
        det = beta1 * beta2 - a1e * a2e
    g1 = (-beta2 - a2e) / det
    g2 = (a1e + beta1) / det

    t2 = 12.0 * sv1
    if t2 > 1.0:
        t2 = 1.0
    if t2 < -1.0:
        t2 = -1.0
    v1a = v1 + t2
    t2 = 12.0 * sv2
    if t2 > 1.0:
        t2 = 1.0
    if t2 < -1.0:
        t2 = -1.0
    v2a = v2 + t2

    h3cap = ulim - 0.04
    if h3cap > 0.71:
        h3cap = 0.71
    if h3cap < 0.30:
        h3cap = 0.30
    h4cap = h3cap
    vcap = 11.7
    vmin = 1.3

    h1slo = 0.02
    if splo > h1slo:
        h1slo = splo
    h1shi = 1.5
    if sphi < h1shi:
        h1shi = sphi
    h2slo = 0.02
    if splo > h2slo:
        h2slo = splo
    if h2lo_b > h2slo:
        h2slo = h2lo_b
    h2shi = 1.5
    if sphi < h2shi:
        h2shi = sphi
    if h2hi_b < h2shi:
        h2shi = h2hi_b

    def pen(dv):
        Q1 = s * Q1N - dv
        Q2 = s * Q2N + dv
        vv1 = v1a + g1 * (dv - d0)
        vv2 = v2a + g2 * (dv - d0)
        p = 16.0 * abs(dv - d0)
        h1p = (Q1 / C1) ** 2 if Q1 > 0.0 else 0.0
        h2p = (Q2 / C2) ** 2 if Q2 > 0.0 else 0.0
        h3p = (a2e * vv2 / C3) ** 2 if vv2 > 0.0 else 0.0
        h4p = (a1e * vv1 / C4) ** 2 if vv1 > 0.0 else 0.0
        if h3p > h3cap:
            p += 3000.0 * (h3p - h3cap)
        if h4p > h4cap:
            p += 3000.0 * (h4p - h4cap)
        bb = h2slo + 0.010
        if h2p < bb:
            p += 3000.0 * (bb - h2p)
        bb = h2shi - 0.010
        if h2p > bb:
            p += 3000.0 * (h2p - bb)
        bb = h1slo + 0.010
        if h1p < bb:
            p += 8000.0 * (bb - h1p)
        bb = h1shi - 0.010
        if h1p > bb:
            p += 8000.0 * (h1p - bb)
        if vv1 > vcap:
            p += 120.0 * (vv1 - vcap)
        if vv1 < vmin:
            p += 120.0 * (vmin - vv1)
        if vv2 > vcap:
            p += 120.0 * (vv2 - vcap)
        if vv2 < vmin:
            p += 120.0 * (vmin - vv2)
        return p

    best = d0
    bestp = pen(d0)
    for i in range(301):
        dv = -3.0 + 0.02 * i
        pp = pen(dv)
        if pp < bestp:
            bestp = pp
            best = dv
    if abs(best - d0) < 0.025:
        best = d0
    dst = best

    Q1f = s * Q1N - dst
    Q2f = s * Q2N + dst
    if Q1f < 0.0:
        Q1f = 0.0
    if Q2f < 0.0:
        Q2f = 0.0
    h1s = (Q1f / C1) ** 2
    h2s = (Q2f / C2) ** 2
    if h1s < h1slo:
        h1s = h1slo
    if h1s > h1shi:
        h1s = h1shi
    if h2s < h2slo:
        h2s = h2slo
    if h2s > h2shi:
        h2s = h2shi

    v1p = v1a + g1 * (dst - d0)
    v2p = v2a + g2 * (dst - d0)
    h3p = (a2e * v2p / C3) ** 2 if v2p > 0.0 else 0.0
    h4p = (a1e * v1p / C4) ** 2 if v1p > 0.0 else 0.0
    diag = "shift %+.3f L/s h3p %.2f h4p %.2f v1p %.1f v2p %.1f" % (dst, h3p, h4p, v1p, v2p)
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1s, "h2": h2s}}
