def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1 = 0.0035
    a2 = 0.0030
    a3 = 0.0020
    a4 = 0.0025
    k1n = 0.00085
    k2n = 0.00095
    K1n = 0.8 * k1n
    K2n = 0.8 * k2n
    QNOM = 16.35286638873749
    HN1 = 0.30
    HN2 = 0.35
    rt2g = math.sqrt(2.0 * g)

    def sq(x):
        if x <= 0.0:
            return 0.0
        return math.sqrt(x)

    def outflow(h, a):
        if h <= 0.0:
            return 0.0
        return a * rt2g * sq(h)

    W = telemetry_window
    n = len(W)
    ph1 = float(active_setpoints["h1"])
    ph2 = float(active_setpoints["h2"])
    sp_lo = float(objectives["setpoint_limits"][0])
    sp_hi = float(objectives["setpoint_limits"][1])
    target = float(objectives["production_target"])
    Qt = target / 1000.0
    band_lo = float(objectives["h2_band"][0])
    band_hi = float(objectives["h2_band"][1])
    Hlim = float(objectives["upper_level_limit"])

    if n < 20 or Qt <= 0.0:
        return {"diagnosis": "insufficient telemetry; holding setpoints",
                "adjusted_setpoints": {"h1": min(sp_hi, max(sp_lo, ph1)),
                                       "h2": min(sp_hi, max(sp_lo, ph2))}}

    # ---- upper-tank outflow coefficients K1=(1-gamma1)k1, K2=(1-gamma2)k2 ----
    # exact identity:  dh3/dt = -a3*sqrt(2g*h3) + K2*v2   (same for tank4)
    i0 = n - 1 - 80
    if i0 < 1:
        i0 = 1
    sK1 = 0.0
    cK1 = 0
    sK2 = 0.0
    cK2 = 0
    for i in range(i0, n):
        dt = W[i]["time"] - W[i - 1]["time"]
        if dt <= 0.0:
            continue
        v2 = W[i]["v2"]
        if v2 > 2.0:
            o3 = a3 * rt2g * sq(W[i]["h3"])
            sK2 += ((W[i]["h3"] - W[i - 1]["h3"]) / dt + o3) / v2
            cK2 += 1
        v1 = W[i]["v1"]
        if v1 > 2.0:
            o4 = a4 * rt2g * sq(W[i]["h4"])
            sK1 += ((W[i]["h4"] - W[i - 1]["h4"]) / dt + o4) / v1
            cK1 += 1

    if cK1 >= 15:
        K1e = sK1 / cK1
    else:
        K1e = K1n
    if cK2 >= 15:
        K2e = sK2 / cK2
    else:
        K2e = K2n
    K1e = min(max(K1e, 0.35 * K1n), 1.30 * K1n)
    K2e = min(max(K2e, 0.35 * K2n), 1.30 * K2n)
    G1e = k1n - K1e
    G2e = k2n - K2e
    G1e = min(max(G1e, 0.02 * k1n), 0.90 * k1n)
    G2e = min(max(G2e, 0.02 * k2n), 0.90 * k2n)

    # ---- unmeasured feed terms, from the lower-tank balances, recent window ----
    i1 = n - 1 - 30
    if i1 < 1:
        i1 = 1
    sd1 = 0.0
    cd1 = 0
    sd2 = 0.0
    cd2 = 0
    for i in range(i1, n):
        dt = W[i]["time"] - W[i - 1]["time"]
        if dt <= 0.0:
            continue
        o1 = a1 * rt2g * sq(W[i]["h1"])
        sd1 += (W[i]["h1"] - W[i - 1]["h1"]) / dt + o1 - K2e * W[i]["v2"] - G1e * W[i]["v1"]
        cd1 += 1
        o2 = a2 * rt2g * sq(W[i]["h2"])
        sd2 += (W[i]["h2"] - W[i - 1]["h2"]) / dt + o2 - K1e * W[i]["v1"] - G2e * W[i]["v2"]
        cd2 += 1

    if cd1 > 0:
        d1e = sd1 / cd1
    else:
        d1e = 0.0
    if cd2 > 0:
        d2e = sd2 / cd2
    else:
        d2e = 0.0
    d1e = min(max(d1e, -0.006), 0.006)
    d2e = min(max(d2e, -0.006), 0.006)

    det = G1e * G2e - K1e * K2e
    if det > -1.0e-9:
        det = -1.0e-9

    def predict(o1, o2):
        v1 = (G2e * (o1 - d1e) - K2e * (o2 - d2e)) / det
        v2 = (G1e * (o2 - d2e) - K1e * (o1 - d1e)) / det
        h3 = (K2e * v2) * (K2e * v2) / (2.0 * g * a3 * a3)
        h4 = (K1e * v1) * (K1e * v1) / (2.0 * g * a4 * a4)
        return v1, v2, h3, h4

    def h2_for(h1):
        o1 = outflow(h1, a1)
        o2 = Qt - o1
        if o2 <= 1.0e-7:
            return None
        return (o2 / a2) * (o2 / a2) / (2.0 * g)

    h3_lim = Hlim - 0.03
    h4_lim = Hlim - 0.03
    v_lim = 12.0 - 0.35

    def violation(h1):
        h2c = h2_for(h1)
        if h2c is None:
            return 1.0e6
        o1 = outflow(h1, a1)
        o2 = Qt - o1
        v1, v2, h3, h4 = predict(o1, o2)
        x = 0.0
        x += max(0.0, h3 - h3_lim)
        x += max(0.0, h4 - h4_lim)
        x += max(0.0, h2c - (band_hi - 0.01))
        x += max(0.0, (band_lo + 0.01) - h2c)
        x += max(0.0, v1 - v_lim)
        x += max(0.0, v2 - v_lim)
        x += max(0.0, 1.0 - v1)
        x += max(0.0, 1.0 - v2)
        x += max(0.0, h1 - 1.45) + max(0.0, 0.025 - h1)
        x += max(0.0, h2c - 1.45) + max(0.0, 0.025 - h2c)
        return x

    q_prev = outflow(ph1, a1) + outflow(ph2, a2)
    if abs(q_prev - Qt) <= 0.0025 * Qt:
        des_h1 = ph1
    else:
        s = (target / QNOM) * (target / QNOM)
        des_h1 = HN1 * s

    hicap = (0.99 * Qt / (a1 * rt2g)) * (0.99 * Qt / (a1 * rt2g))
    if hicap > 1.2:
        hicap = 1.2
    h1_lo = 0.03
    if hicap < h1_lo + 0.05:
        hicap = h1_lo + 0.05
    if des_h1 < h1_lo:
        des_h1 = h1_lo
    if des_h1 > hicap:
        des_h1 = hicap

    NG = 200
    grid = []
    for k in range(NG):
        hh = h1_lo + (hicap - h1_lo) * k / (NG - 1.0)
        grid.append((hh, violation(hh)))

    runs = []
    cur_a = -1
    cur_b = -1
    for k in range(NG):
        if grid[k][1] <= 1.0e-9:
            if cur_a < 0:
                cur_a = k
                cur_b = k
            else:
                cur_b = k
        else:
            if cur_a >= 0:
                runs.append((cur_a, cur_b))
                cur_a = -1
                cur_b = -1
    if cur_a >= 0:
        runs.append((cur_a, cur_b))

    diag = "ok"
    if runs:
        best = None
        bestd = None
        for r in runs:
            lo = grid[r[0]][0]
            hi = grid[r[1]][0]
            if des_h1 < lo:
                dd = lo - des_h1
            elif des_h1 > hi:
                dd = des_h1 - hi
            else:
                dd = 0.0
            if bestd is None or dd < bestd:
                bestd = dd
                best = r
        klo = best[0]
        khi = best[1]
        if klo > 0:
            xa = grid[klo - 1][0]
            xb = grid[klo][0]
            for _ in range(24):
                xm = 0.5 * (xa + xb)
                if violation(xm) <= 1.0e-9:
                    xb = xm
                else:
                    xa = xm
            lo_ref = xb
        else:
            lo_ref = grid[0][0]
        if khi < NG - 1:
            xa = grid[khi][0]
            xb = grid[khi + 1][0]
            for _ in range(24):
                xm = 0.5 * (xa + xb)
                if violation(xm) <= 1.0e-9:
                    xa = xm
                else:
                    xb = xm
            hi_ref = xa
        else:
            hi_ref = grid[NG - 1][0]
        h1_cmd = min(max(des_h1, lo_ref), hi_ref)
    else:
        bestc = None
        h1_cmd = des_h1
        for k in range(NG):
            hh = grid[k][0]
            cc = grid[k][1] + 0.05 * abs(hh - des_h1)
            if bestc is None or cc < bestc:
                bestc = cc
                h1_cmd = hh
        diag = "infeasible; minimising violations"

    h2_cmd = h2_for(h1_cmd)
    if h2_cmd is None:
        h2_cmd = ph2

    if abs(h1_cmd - ph1) < 0.002 and abs(h2_cmd - ph2) < 0.002:
        h1_cmd = ph1
        h2_cmd = ph2

    h1_cmd = min(sp_hi, max(sp_lo, h1_cmd))
    h2_cmd = min(sp_hi, max(sp_lo, h2_cmd))

    msg = ("K1=" + str(round(K1e, 6)) + " K2=" + str(round(K2e, 6))
           + " G1=" + str(round(G1e, 6)) + " G2=" + str(round(G2e, 6))
           + " d1=" + str(round(d1e, 5)) + " d2=" + str(round(d2e, 5))
           + " | " + diag
           + " | h1 " + str(round(ph1, 3)) + "->" + str(round(h1_cmd, 3))
           + " h2 " + str(round(ph2, 3)) + "->" + str(round(h2_cmd, 3)))
    return {"diagnosis": msg, "adjusted_setpoints": {"h1": h1_cmd, "h2": h2_cmd}}
