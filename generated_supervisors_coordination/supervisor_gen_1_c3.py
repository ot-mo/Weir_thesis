def supervise(telemetry_window, active_setpoints, objectives):
    G2 = 19.62
    A1 = 0.0035
    A2 = 0.003
    A3 = 0.002
    A4 = 0.0025
    K1 = 0.00085
    K2 = 0.00095
    GAM1 = 0.20
    GAM2 = 0.20

    def qof(h, a):
        if h <= 0.0:
            return 0.0
        return a * math.sqrt(G2 * h)

    def hof(q, a):
        if q <= 0.0:
            return 0.0
        return (q / a) * (q / a) / G2

    g1n = GAM1 * K1
    g2n = GAM2 * K2
    c3n = (1.0 - GAM2) * K2
    c4n = (1.0 - GAM1) * K1
    k1n = c4n + g1n
    k2n = c3n + g2n
    Dn = c3n * c4n - g1n * g2n
    q1nom = qof(0.30, A1)
    q2nom = qof(0.35, A2)
    Qnom = q1nom + q2nom

    w = telemetry_window
    n = len(w)
    last = w[n - 1]
    Qtar = float(last["production_target"]) * 0.001
    lim = float(objectives.get("upper_level_limit", 0.75))
    band = objectives.get("h2_band", [0.25, 0.45])
    band_lo = float(band[0])
    band_hi = float(band[1])
    splim = objectives.get("setpoint_limits", [0.0, 1.5])
    spl_lo = float(splim[0])
    spl_hi = float(splim[1])
    SAFE_LO = 0.02
    SAFE_HI = 1.5
    PMIN = 1.0
    PMAX = 12.0
    h1c = float(active_setpoints["h1"])
    h2c = float(active_setpoints["h2"])

    # ---- locate an estimation region (avoid our own fresh setpoint transient) ----
    change_idx = -1
    for j in range(n - 1, 0, -1):
        if (w[j]["sp_h1"], w[j]["sp_h2"]) != (w[j - 1]["sp_h1"], w[j - 1]["sp_h2"]):
            change_idx = j
            break
    if change_idx > 0 and (n - 1 - change_idx) < 120:
        end_est = change_idx
    else:
        end_est = n
    if end_est < 15:
        end_est = n

    # ---- effective upper-tank flow coefficients from last steady-ish sample ----
    se = w[end_est - 1]
    c3e = qof(se["h3"], A3) / max(se["v2"], 0.3)
    c4e = qof(se["h4"], A4) / max(se["v1"], 0.3)
    c3e = min(max(c3e, 0.30 * c3n), 2.5 * c3n)
    c4e = min(max(c4e, 0.30 * c4n), 2.5 * c4n)
    g1e = c4e * GAM1 / (1.0 - GAM1)
    g2e = c3e * GAM2 / (1.0 - GAM2)

    # ---- oscillation guard ----
    a0 = max(1, end_est - 100)
    sc = 0
    prev = 0
    for i in range(a0, end_est):
        d = w[i]["h1"] - w[i - 1]["h1"]
        sgn = 1 if d > 0.0006 else (-1 if d < -0.0006 else 0)
        if sgn != 0 and prev != 0 and sgn != prev:
            sc += 1
        if sgn != 0:
            prev = sgn
    osc = sc >= 9

    # ---- average additive disturbance estimate ----
    d1a = 0.0
    d2a = 0.0
    cnt = 0
    b0 = max(12, end_est - 40)
    for i in range(b0, end_est):
        si = w[i]
        j = i - 10
        dh1 = (si["h1"] - w[j]["h1"]) / 10.0
        dh2 = (si["h2"] - w[j]["h2"]) / 10.0
        q1i = qof(si["h1"], A1)
        q2i = qof(si["h2"], A2)
        u3i = qof(si["h3"], A3)
        u4i = qof(si["h4"], A4)
        d1a += dh1 + q1i - u3i - g1e * si["v1"]
        d2a += dh2 + q2i - u4i - g2e * si["v2"]
        cnt += 1
    if cnt > 0:
        d1 = d1a / cnt
        d2 = d2a / cnt
    else:
        d1 = 0.0
        d2 = 0.0
    if osc:
        d1 = 0.0
        d2 = 0.0
        c3e = c3n
        c4e = c4n
        g1e = g1n
        g2e = g2n
    d1 = min(max(d1, -0.008), 0.008)
    d2 = min(max(d2, -0.008), 0.008)

    k1e = c4e + g1e
    k2e = c3e + g2e
    De = c3e * c4e - g1e * g2e
    if De < 1e-9 or k1e < 1e-9 or k2e < 1e-9:
        c3e = c3n
        c4e = c4n
        g1e = g1n
        g2e = g2n
        k1e = k1n
        k2e = k2n
        De = Dn

    # ---- pump-voltage ceilings implied by upper-level limits ----
    caps = lim * 0.99
    V2max = min(PMAX, A3 * math.sqrt(G2 * caps) / c3e)
    V1max = min(PMAX, A4 * math.sqrt(G2 * caps) / c4e)
    if V2max < PMIN + 0.05:
        V2max = PMIN + 0.05
    if V1max < PMIN + 0.05:
        V1max = PMIN + 0.05

    q2max = min(qof(band_hi, A2), qof(SAFE_HI, A2))
    q2min = max(qof(band_lo, A2), qof(SAFE_LO, A2))
    q1min_safe = qof(SAFE_LO, A1)
    q1max_safe = qof(SAFE_HI, A1)

    def interval(Q):
        lo = -1.0
        hi = 1.0
        v = (g2e * d1 + c3e * (Q - d2) - De * V1max) / k2e
        if v > lo:
            lo = v
        v = (g2e * d1 + c3e * (Q - d2) - De * PMIN) / k2e
        if v < hi:
            hi = v
        v = (De * V2max + c4e * d1 + g1e * (Q - d2)) / k1e
        if v < hi:
            hi = v
        v = (De * PMIN + c4e * d1 + g1e * (Q - d2)) / k1e
        if v > lo:
            lo = v
        if Q - q2max > lo:
            lo = Q - q2max
        if Q - q2min < hi:
            hi = Q - q2min
        if q1min_safe > lo:
            lo = q1min_safe
        if q1max_safe < hi:
            hi = q1max_safe
        return lo, hi

    # ---- closest reachable production if target is infeasible ----
    lo, hi = interval(Qtar)
    Qeff = Qtar
    if lo > hi:
        step = Qnom * 0.004
        bestdist = None
        Qcand = None
        for i in range(1, 220):
            for sgn in (1.0, -1.0):
                Qc = Qtar + sgn * i * step
                if Qc <= 0.0005:
                    continue
                l2, h2v = interval(Qc)
                if l2 <= h2v:
                    dd = abs(Qc - Qtar)
                    if bestdist is None or dd < bestdist:
                        bestdist = dd
                        Qcand = Qc
            if Qcand is not None:
                break
        if Qcand is not None:
            Qeff = Qcand

    # ---- minimum-travel feasible split ----
    lo, hi = interval(Qeff)
    if lo > hi:
        mid = 0.5 * (lo + hi)
        lo = mid
        hi = mid
    NSTEP = 48
    bestcost = None
    bh1 = h1c
    bh2 = h2c
    for i in range(NSTEP + 1):
        q1 = lo + (hi - lo) * i / NSTEP
        hh1 = hof(q1, A1)
        hh2 = hof(Qeff - q1, A2)
        cost = abs(hh1 - h1c) + abs(hh2 - h2c)
        if bestcost is None or cost < bestcost:
            bestcost = cost
            bh1 = hh1
            bh2 = hh2
    bh1 = min(spl_hi, max(spl_lo, bh1))
    bh2 = min(spl_hi, max(spl_lo, bh2))

    # ---- deadband: hold if already acceptable ----
    travel = abs(bh1 - h1c) + abs(bh2 - h2c)
    Qcur = qof(h1c, A1) + qof(h2c, A2)
    tol = Qtar * 0.02
    if tol < 0.0002:
        tol = 0.0002
    if travel < 0.012 and abs(Qcur - Qtar) < tol:
        bh1 = h1c
        bh2 = h2c
        diag = "hold: active setpoints already feasible and on target"
    elif Qeff < Qtar - 1e-6:
        diag = "shift split toward other tank; target clamped to keep h3/h4 below limit"
    elif abs(Qeff - Qtar) < 1e-6:
        diag = "move split minimally to satisfy limits at target production"
    else:
        diag = "adjusted split for target and constraints"

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"h1": float(bh1), "h2": float(bh2)},
    }
