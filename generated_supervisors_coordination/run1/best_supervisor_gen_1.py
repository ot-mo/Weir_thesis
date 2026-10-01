def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    c = math.sqrt(2.0 * 9.81)
    QNOM = 16.35286638873749
    S34 = 0.8 / 0.6
    DV1 = 0.001 / (0.6 * k1)
    DV2 = 0.001 / (0.6 * k2)

    try:
        h1a = float(active_setpoints["h1"])
        h2a = float(active_setpoints["h2"])
    except Exception:
        h1a = 0.30
        h2a = 0.35
    fallback = {"diagnosis": "hold setpoints", "adjusted_setpoints": {"h1": h1a, "h2": h2a}}

    try:
        Q_t = float(objectives["production_target"])
        band = objectives["h2_band"]
        h2lo = float(band[0])
        h2hi = float(band[1])
        ulim = float(objectives["upper_level_limit"])
        lim = objectives["setpoint_limits"]
        splo = float(lim[0])
        sphi = float(lim[1])

        n = len(telemetry_window)
        m = 12
        if n < m:
            m = n
        if m < 1:
            return fallback
        tail = telemetry_window[n - m:]

        def fit(key):
            vals = []
            for row in tail:
                vals.append(float(row[key]))
            mm = len(vals)
            if mm < 2:
                return vals[0], 0.0
            mt = (mm - 1) * 0.5
            num = 0.0
            den = 0.0
            s = 0.0
            for i in range(mm):
                d = i - mt
                num += d * vals[i]
                den += d * d
                s += vals[i]
            sl = num / den if den > 0.0 else 0.0
            mean = s / mm
            return mean + sl * (mm - 1 - mt), sl

        h1, sh1 = fit("h1")
        h2, sh2 = fit("h2")
        h3, sh3 = fit("h3")
        h4, sh4 = fit("h4")
        v1, sv1 = fit("v1")
        v2, sv2 = fit("v2")
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

    infl3 = 1000.0 * (a3 * c * math.sqrt(h3) + sh3)
    infl4 = 1000.0 * (a4 * c * math.sqrt(h4) + sh4)

    scale = (Q_t / QNOM) ** 2 if QNOM > 0.0 else 1.0
    h1n = 0.30 * scale
    h2n = 0.35 * scale

    h1_lo = 0.02
    if splo > h1_lo:
        h1_lo = splo
    h1_hi = 1.5
    if sphi < h1_hi:
        h1_hi = sphi
    h2_lo = 0.02
    if splo > h2_lo:
        h2_lo = splo
    if h2lo > h2_lo:
        h2_lo = h2lo
    h2_hi = 1.5
    if sphi < h2_hi:
        h2_hi = sphi
    if h2hi < h2_hi:
        h2_hi = h2hi
    if h2_hi - h2_lo > 0.04:
        h2_lo = h2_lo + 0.005
        h2_hi = h2_hi - 0.005
    if h1_hi - h1_lo > 0.04:
        h1_lo = h1_lo + 0.002
        h1_hi = h1_hi - 0.002

    h1nc = h1n
    if h1nc < h1_lo:
        h1nc = h1_lo
    if h1nc > h1_hi:
        h1nc = h1_hi
    h2nc = h2n
    if h2nc < h2_lo:
        h2nc = h2_lo
    if h2nc > h2_hi:
        h2nc = h2_hi
    Q1n = 1000.0 * a1 * c * math.sqrt(h1nc)
    Q2n = 1000.0 * a2 * c * math.sqrt(h2nc)

    Q1lo = 1000.0 * a1 * c * math.sqrt(h1_lo)
    Q1hi = 1000.0 * a1 * c * math.sqrt(h1_hi)
    Q2lo = 1000.0 * a2 * c * math.sqrt(h2_lo)
    Q2hi = 1000.0 * a2 * c * math.sqrt(h2_hi)

    hardLB = Q1n - Q1hi
    t = Q2lo - Q2n
    if t > hardLB:
        hardLB = t
    hardUB = Q1n - Q1lo
    t = Q2hi - Q2n
    if t < hardUB:
        hardUB = t

    h3t = ulim - 0.05
    if 0.9 * ulim < h3t:
        h3t = 0.9 * ulim
    if h3t < 0.0:
        h3t = 0.0
    infl3t = 1000.0 * a3 * c * math.sqrt(h3t)
    infl4t = 1000.0 * a4 * c * math.sqrt(h3t)

    softLB = (infl3 - infl3t) / S34
    softUB = (infl4t - infl4) / S34

    v1cap = 11.7
    v2cap = 11.7
    v1min = 1.2
    v2min = 1.2
    lbv1 = (v1min - v1) / DV1
    ubv1 = (v1cap - v1) / DV1
    lbv2 = (v2 - v2cap) / DV2
    ubv2 = (v2 - v2min) / DV2

    goalLB = softLB
    if lbv1 > goalLB:
        goalLB = lbv1
    if lbv2 > goalLB:
        goalLB = lbv2
    goalUB = softUB
    if ubv1 < goalUB:
        goalUB = ubv1
    if ubv2 < goalUB:
        goalUB = ubv2

    Q1a = 1000.0 * a1 * c * math.sqrt(max(h1a, 0.0))
    Q2a = 1000.0 * a2 * c * math.sqrt(max(h2a, 0.0))
    dref = 0.5 * ((Q1n - Q1a) + (Q2a - Q2n))

    lo = hardLB
    if goalLB > lo:
        lo = goalLB
    hi = hardUB
    if goalUB < hi:
        hi = goalUB

    if lo <= hi:
        delta = dref
        if delta < lo:
            delta = lo
        if delta > hi:
            delta = hi
    else:
        delta = 0.5 * (goalLB + goalUB)
        if delta < hardLB:
            delta = hardLB
        if delta > hardUB:
            delta = hardUB

    delta = dref + 0.8 * (delta - dref)
    if delta < hardLB:
        delta = hardLB
    if delta > hardUB:
        delta = hardUB

    Q1 = Q1n - delta
    Q2 = Q2n + delta
    if Q1 < 0.0:
        Q1 = 0.0
    if Q2 < 0.0:
        Q2 = 0.0
    h1s = (Q1 / (1000.0 * a1 * c)) ** 2
    h2s = (Q2 / (1000.0 * a2 * c)) ** 2
    if h1s < h1_lo:
        h1s = h1_lo
    if h1s > h1_hi:
        h1s = h1_hi
    if h2s < h2_lo:
        h2s = h2_lo
    if h2s > h2_hi:
        h2s = h2_hi

    p3 = (infl3 - S34 * delta) / (1000.0 * a3 * c)
    p4 = (infl4 + S34 * delta) / (1000.0 * a4 * c)
    diag = "shift=%+.3f L/s; h3_ss=%.2f h4_ss=%.2f; v1=%.1f v2=%.1f" % (delta, p3 * p3, p4 * p4, v1, v2)

    return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1s, "h2": h2s}}
