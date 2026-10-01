def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    gam1 = 0.20
    gam2 = 0.20
    g = 9.81
    s2g = (2.0 * g) ** 0.5
    cb = gam1 * k1
    cd = gam2 * k2
    G3 = (1.0 - gam2) * k2
    G4 = (1.0 - gam1) * k1
    Det = G3 * G4 - cb * cd
    if abs(Det) < 1e-15:
        Det = 1e-15

    Q = float(objectives["production_target"])
    band = objectives["h2_band"]
    h2_lo = float(band[0])
    h2_hi = float(band[1])
    upper_lim = float(objectives["upper_level_limit"])
    lims = objectives["setpoint_limits"]
    sp_lo = float(lims[0])
    sp_hi = float(lims[1])

    C = Q / (1000.0 * s2g)
    if C < 1e-9:
        C = 1e-9

    last = telemetry_window[-1]
    h1m = float(last["h1"])
    h2m = float(last["h2"])
    h3m = float(last["h3"])
    h4m = float(last["h4"])
    v1m = float(last["v1"])
    v2m = float(last["v2"])

    nw = len(telemetry_window)
    m = 10
    if m > nw - 1:
        m = nw - 1
    if m < 1:
        m = 1
    t1 = float(telemetry_window[-1]["time"])
    t0 = float(telemetry_window[-1 - m]["time"])
    dt = t1 - t0
    if dt <= 0.0:
        dt = 1.0
    dh1 = (float(telemetry_window[-1]["h1"]) - float(telemetry_window[-1 - m]["h1"])) / dt
    dh2 = (float(telemetry_window[-1]["h2"]) - float(telemetry_window[-1 - m]["h2"])) / dt

    d1 = dh1 + a1 * s2g * math.sqrt(max(h1m, 0.0)) - a3 * s2g * math.sqrt(max(h3m, 0.0)) - cb * v1m
    d2 = dh2 + a2 * s2g * math.sqrt(max(h2m, 0.0)) - a4 * s2g * math.sqrt(max(h4m, 0.0)) - cd * v2m

    h1a = float(active_setpoints["h1"])
    h2a = float(active_setpoints["h2"])

    h3_soft = upper_lim - 0.015
    h4_soft = upper_lim - 0.015
    band_hi = h2_hi - 0.005
    band_lo = h2_lo + 0.005

    bestcost = None
    besth1 = h1a
    besth2 = h2a

    N = 300
    i = 0
    while i <= N:
        f = i / float(N)
        i += 1
        if f <= 0.0 or f >= 1.0:
            continue
        h1 = (f * C / a1) ** 2
        h2 = ((1.0 - f) * C / a2) ** 2
        if h1 < sp_lo or h1 > sp_hi or h2 < sp_lo or h2 > sp_hi:
            continue
        P1 = a1 * s2g * math.sqrt(h1) - d1
        P2 = a2 * s2g * math.sqrt(h2) - d2
        v2 = (P1 * G4 - cb * P2) / Det
        v1 = (G3 * P2 - cd * P1) / Det
        if v2 > 0.0:
            h3 = (G3 * v2 / a3) ** 2 / (2.0 * g)
        else:
            h3 = 0.0
        if v1 > 0.0:
            h4 = (G4 * v1 / a4) ** 2 / (2.0 * g)
        else:
            h4 = 0.0
        cost = 100.0 * (abs(h1 - h1a) + abs(h2 - h2a))
        cost += 30000.0 * max(0.0, h3 - h3_soft)
        cost += 30000.0 * max(0.0, h4 - h4_soft)
        cost += 40000.0 * max(0.0, h2 - band_hi)
        cost += 40000.0 * max(0.0, band_lo - h2)
        cost += 300000.0 * max(0.0, h1 - 1.4)
        cost += 300000.0 * max(0.0, 0.03 - h1)
        cost += 300000.0 * max(0.0, h2 - 1.4)
        cost += 300000.0 * max(0.0, 0.03 - h2)
        cost += 5000.0 * max(0.0, v2 - 12.0)
        cost += 5000.0 * max(0.0, v1 - 12.0)
        if bestcost is None or cost < bestcost:
            bestcost = cost
            besth1 = h1
            besth2 = h2

    if bestcost is None:
        return {
            "diagnosis": "no feasible split; holding active setpoints",
            "adjusted_setpoints": {"h1": h1a, "h2": h2a},
        }

    travel = abs(besth1 - h1a) + abs(besth2 - h2a)
    Qact = 1000.0 * s2g * (a1 * math.sqrt(max(h1a, 0.0)) + a2 * math.sqrt(max(h2a, 0.0)))
    if travel < 0.015 and abs(Qact - Q) < 0.2:
        return {
            "diagnosis": "constraints satisfied; holding setpoints",
            "adjusted_setpoints": {"h1": h1a, "h2": h2a},
        }

    h1o = min(sp_hi, max(sp_lo, besth1))
    h2o = min(sp_hi, max(sp_lo, besth2))
    return {
        "diagnosis": "re-balanced production split to respect tank limits",
        "adjusted_setpoints": {"h1": h1o, "h2": h2o},
    }
