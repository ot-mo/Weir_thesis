def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1n = 0.00085
    k2n = 0.00095
    gm1 = 0.20
    gm2 = 0.20
    p1n = gm1 * k1n
    p2n = (1.0 - gm1) * k1n
    p3n = gm2 * k2n
    p4n = (1.0 - gm2) * k2n
    c1 = a1 * math.sqrt(2.0 * g)
    c2 = a2 * math.sqrt(2.0 * g)

    sp1 = 0.30
    sp2 = 0.35
    try:
        sp1 = float(active_setpoints["h1"])
        sp2 = float(active_setpoints["h2"])
    except Exception:
        sp1 = 0.30
        sp2 = 0.35

    Qt = 0.01635
    band_lo = 0.25
    band_hi = 0.45
    Lu = 0.75
    slo = 0.05
    shi = 1.20
    try:
        Qt = float(objectives["production_target"]) / 1000.0
        bl = objectives["h2_band"]
        band_lo = float(bl[0])
        band_hi = float(bl[1])
        Lu = float(objectives["upper_level_limit"])
        sl = objectives["setpoint_limits"]
        slo = float(sl[0])
        shi = float(sl[1])
    except Exception:
        pass
    if Qt < 1e-6:
        Qt = 1e-6
    if slo < 0.02:
        slo = 0.02
    if shi > 1.5:
        shi = 1.5
    if shi <= slo:
        shi = slo + 0.5

    w = telemetry_window
    n = len(w)
    if n < 3:
        return {"diagnosis": "no telemetry; holding setpoints",
                "adjusted_setpoints": {"h1": sp1, "h2": sp2}}

    start = n - 25
    if start < 1:
        start = 1
    s3r = 0.0
    s3v = 0.0
    s4r = 0.0
    s4v = 0.0
    cnt = 0
    for i in range(start, n):
        cur = w[i]
        prv = w[i - 1]
        dt = cur["time"] - prv["time"]
        if dt <= 0.0:
            dt = 1.0
        dh3 = (cur["h3"] - prv["h3"]) / dt
        dh4 = (cur["h4"] - prv["h4"]) / dt
        s3r += dh3 + a3 * math.sqrt(2.0 * g * cur["h3"]) - p4n * cur["v2"]
        s3v += cur["v2"]
        s4r += dh4 + a4 * math.sqrt(2.0 * g * cur["h4"]) - p2n * cur["v1"]
        s4v += cur["v1"]
        cnt += 1
    cn = float(cnt)
    mv1 = s4v / cn
    mv2 = s3v / cn
    K4 = p2n
    if mv1 > 1e-6:
        K4 = p2n - (s4r / cn) / mv1
    K3 = p4n
    if mv2 > 1e-6:
        K3 = p4n - (s3r / cn) / mv2
    if K4 < 0.3 * p2n or K4 > 2.0 * p2n:
        K4 = p2n
    if K3 < 0.3 * p4n or K3 > 2.0 * p4n:
        K3 = p4n
    p2 = K4
    p4 = K3
    p1 = K4 * (gm1 / (1.0 - gm1))
    p3 = K3 * (gm2 / (1.0 - gm2))

    sd1 = 0.0
    sd2 = 0.0
    for i in range(start, n):
        cur = w[i]
        prv = w[i - 1]
        dt = cur["time"] - prv["time"]
        if dt <= 0.0:
            dt = 1.0
        dh1 = (cur["h1"] - prv["h1"]) / dt
        dh2 = (cur["h2"] - prv["h2"]) / dt
        sd1 += (dh1 + a1 * math.sqrt(2.0 * g * cur["h1"])
                - a3 * math.sqrt(2.0 * g * cur["h3"]) - p1 * cur["v1"])
        sd2 += (dh2 + a2 * math.sqrt(2.0 * g * cur["h2"])
                - a4 * math.sqrt(2.0 * g * cur["h4"]) - p3 * cur["v2"])
    d1 = sd1 / cn
    d2 = sd2 / cn
    if d1 > 0.006:
        d1 = 0.006
    if d1 < -0.006:
        d1 = -0.006
    if d2 > 0.006:
        d2 = 0.006
    if d2 < -0.006:
        d2 = -0.006

    D = p1 * p3 - p4 * p2
    if D > -1e-12:
        p1 = p1n
        p2 = p2n
        p3 = p3n
        p4 = p4n
        D = p1 * p3 - p4 * p2

    VMIN = 1.0
    VMAX = 12.0
    h2_lo_c = max(slo, 0.02)
    h2_hi_c = min(shi, 1.40)
    h1_lo_c = max(slo, 0.03)
    h1_hi_c = min(shi, 1.40)
    f1_min = c1 * math.sqrt(h1_lo_c)
    f1_max = c1 * math.sqrt(h1_hi_c)
    t_lo = Qt - c2 * math.sqrt(h2_hi_c)
    t_hi = Qt - c2 * math.sqrt(h2_lo_c)
    if t_lo > f1_min:
        f1_min = t_lo
    if t_hi < f1_max:
        f1_max = t_hi
    if f1_max <= f1_min:
        f1_min = 0.05 * Qt
        f1_max = 0.95 * Qt
    if f1_max <= f1_min:
        f1_min = 0.2 * Qt
        f1_max = 0.8 * Qt

    def evalf(fc):
        f2 = Qt - fc
        if f2 <= 0.0:
            return (1e30, sp1, sp2)
        h1d = (fc / c1) * (fc / c1)
        h2d = (f2 / c2) * (f2 / c2)
        v1 = (p3 * (fc - d1) - p4 * (f2 - d2)) / D
        v2 = (p1 * (f2 - d2) - p2 * (fc - d1)) / D
        sat = False
        if v1 > VMAX:
            v1 = VMAX
            sat = True
        elif v1 < VMIN:
            v1 = VMIN
            sat = True
        if v2 > VMAX:
            v2 = VMAX
            sat = True
        elif v2 < VMIN:
            v2 = VMIN
            sat = True
        if sat:
            fa1 = p1 * v1 + p4 * v2 + d1
            fa2 = p2 * v1 + p3 * v2 + d2
            if fa1 < 0.0:
                fa1 = 0.0
            if fa2 < 0.0:
                fa2 = 0.0
            h1a = (fa1 / c1) * (fa1 / c1)
            h2a = (fa2 / c2) * (fa2 / c2)
            prod = fa1 + fa2
        else:
            h1a = h1d
            h2a = h2d
            prod = Qt
        h3 = (p4 * v2) * (p4 * v2) / (a3 * a3 * 2.0 * g)
        h4 = (p2 * v1) * (p2 * v1) / (a4 * a4 * 2.0 * g)
        cost = 0.0
        if h3 > Lu:
            cost += 8000.0 + 100000.0 * (h3 - Lu)
        elif h3 > Lu - 0.03:
            cost += 20000.0 * (h3 - (Lu - 0.03))
        if h4 > Lu:
            cost += 8000.0 + 100000.0 * (h4 - Lu)
        elif h4 > Lu - 0.03:
            cost += 20000.0 * (h4 - (Lu - 0.03))
        if h2a < band_lo:
            cost += 300.0 + 3000.0 * (band_lo - h2a)
        elif h2a > band_hi:
            cost += 300.0 + 3000.0 * (h2a - band_hi)
        else:
            cost += 500.0 * max(0.0, (band_lo + 0.015) - h2a)
            cost += 500.0 * max(0.0, h2a - (band_hi - 0.015))
        if h1a < 0.02 or h1a > 1.5 or h2a < 0.02 or h2a > 1.5:
            cost += 100000.0
        cost += 2.0e6 * abs(prod - Qt)
        if sat:
            cost += 500.0
        cost += 3000.0 * max(0.0, v1 - 11.5) + 3000.0 * max(0.0, v2 - 11.5)
        cost += 100.0 * (abs(h1d - sp1) + abs(h2d - sp2))
        return (cost, h1d, h2d)

    best_cost = 1e29
    best_h1 = sp1
    best_h2 = sp2
    N = 240
    span = f1_max - f1_min
    for j in range(N + 1):
        fc = f1_min + span * (j / float(N))
        cc, h1d, h2d = evalf(fc)
        if cc < best_cost:
            best_cost = cc
            best_h1 = h1d
            best_h2 = h2d
    f1c = c1 * math.sqrt(max(0.0, sp1))
    for fc in (f1c, Qt - c2 * math.sqrt(max(0.0, sp2))):
        if f1_min <= fc <= f1_max:
            cc, h1d, h2d = evalf(fc)
            if cc < best_cost:
                best_cost = cc
                best_h1 = h1d
                best_h2 = h2d

    h1_out = min(shi, max(slo, best_h1))
    h2_out = min(shi, max(slo, best_h2))

    diag = ("target=%.2f L/s, d1=%.4f d2=%.4f m3/s, K3=%.5f K4=%.5f, sp=(%.3f,%.3f)"
            % (Qt * 1000.0, d1, d2, K3, K4, h1_out, h2_out))
    return {"diagnosis": diag,
            "adjusted_setpoints": {"h1": h1_out, "h2": h2_out}}
