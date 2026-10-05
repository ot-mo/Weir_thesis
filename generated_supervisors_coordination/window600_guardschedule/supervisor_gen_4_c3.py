def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    S2 = (2.0 * g) ** 0.5
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    gam1 = 0.20
    gam2 = 0.20
    k1n = 0.00085
    k2n = 0.00095

    W = telemetry_window
    n = len(W)
    last = W[n - 1]
    t_now = last["time"]

    lo_lim = objectives["setpoint_limits"][0]
    hi_lim = objectives["setpoint_limits"][1]
    Q = objectives["production_target"] / 1000.0
    h2_lo = objectives["h2_band"][0]
    h2_hi = objectives["h2_band"][1]
    ulim = objectives["upper_level_limit"]

    def qh(h, a):
        if h <= 0.0:
            return 0.0
        return a * ((2.0 * g * h) ** 0.5)

    def hq(q, a):
        if q <= 0.0:
            return 0.0
        r = q / (a * S2)
        return r * r

    last_change = -1.0e9
    last_tg = -1.0e9
    for i in range(1, n):
        c = W[i]
        p = W[i - 1]
        if abs(c["sp_h1"] - p["sp_h1"]) > 1.0e-9 or abs(c["sp_h2"] - p["sp_h2"]) > 1.0e-9:
            last_change = c["time"]
        if abs(c["production_target"] - p["production_target"]) > 1.0e-9:
            last_tg = c["time"]

    i0 = n - 1
    i1 = n - 16
    if i1 < 0:
        i1 = 0
    dt = W[i0]["time"] - W[i1]["time"]
    if dt <= 0.0:
        dt = 1.0
    s = W[i0]
    s0 = W[i1]
    dh1 = (s["h1"] - s0["h1"]) / dt
    dh2 = (s["h2"] - s0["h2"]) / dt
    dh3 = (s["h3"] - s0["h3"]) / dt
    dh4 = (s["h4"] - s0["h4"]) / dt

    q1m = qh(s["h1"], a1)
    q2m = qh(s["h2"], a2)
    q3m = qh(s["h3"], a3)
    q4m = qh(s["h4"], a4)

    d1 = dh1 + q1m - q3m - (gam1 / (1.0 - gam1)) * q4m
    d2 = dh2 + q2m - q4m - (gam2 / (1.0 - gam2)) * q3m

    k1e = k1n
    k2e = k2n
    v1m = s["v1"]
    v2m = s["v2"]
    if v1m > 0.5:
        t1 = (dh4 + q4m) / ((1.0 - gam1) * v1m)
        if t1 < 0.6 * k1n:
            k1e = 0.6 * k1n
        elif t1 < k1n:
            k1e = t1
    if v2m > 0.5:
        t2 = (dh3 + q3m) / ((1.0 - gam2) * v2m)
        if t2 < 0.6 * k2n:
            k2e = 0.6 * k2n
        elif t2 < k2n:
            k2e = t2

    h1_cur = min(hi_lim, max(lo_lim, active_setpoints["h1"]))
    h2_cur = min(hi_lim, max(lo_lim, active_setpoints["h2"]))

    h1_min = max(0.02, lo_lim)
    h1_max = min(1.5, hi_lim)
    h2_min = max(0.02, lo_lim)
    h2_max = min(1.5, hi_lim)

    q1_lo = qh(h1_min, a1)
    if Q - qh(h2_max, a2) > q1_lo:
        q1_lo = Q - qh(h2_max, a2)
    q1_hi = qh(h1_max, a1)
    if Q - qh(h2_min, a2) < q1_hi:
        q1_hi = Q - qh(h2_min, a2)
    if q1_lo > q1_hi:
        mid = 0.5 * (q1_lo + q1_hi)
        q1_lo = mid
        q1_hi = mid

    q1_cur = qh(h1_cur, a1)
    if q1_cur < q1_lo:
        q1_cur = q1_lo
    if q1_cur > q1_hi:
        q1_cur = q1_hi

    H3t = ulim - 0.04
    H4t = ulim - 0.04
    H2lo = h2_lo + 0.01
    H2hi = h2_hi - 0.01
    vlim = 11.4

    best_q1 = q1_cur
    best_c = None
    N = 80
    for kk in range(N + 1):
        q1 = q1_lo + (q1_hi - q1_lo) * kk / N
        q2 = Q - q1
        if q1 <= 1.0e-7 or q2 <= 1.0e-7:
            continue
        Q1 = q1 - d1
        Q2 = q2 - d2
        k1v1 = (4.0 * Q2 - Q1) / 3.0
        k2v2 = (4.0 * Q1 - Q2) / 3.0
        if k1v1 <= 0.0 or k2v2 <= 0.0:
            continue
        h3p = (0.8 * k2v2 / a3) ** 2 / (2.0 * g)
        h4p = (0.8 * k1v1 / a4) ** 2 / (2.0 * g)
        h1p = hq(q1, a1)
        h2p = hq(q2, a2)
        v1p = k1v1 / k1e
        v2p = k2v2 / k2e
        c = 0.0
        if h3p > H3t:
            c += 3000.0 * (h3p - H3t)
        if h4p > H4t:
            c += 3000.0 * (h4p - H4t)
        if h2p < H2lo:
            c += 3000.0 * (H2lo - h2p)
        if h2p > H2hi:
            c += 3000.0 * (h2p - H2hi)
        if v1p > vlim:
            c += 2000.0 * (v1p - vlim)
        if v2p > vlim:
            c += 2000.0 * (v2p - vlim)
        c += 100.0 * (abs(h1p - h1_cur) + abs(h2p - h2_cur))
        if best_c is None or c < best_c:
            best_c = c
            best_q1 = q1

    h1_des = hq(best_q1, a1)
    h2_des = hq(Q - best_q1, a2)
    h1_des = min(hi_lim, max(lo_lim, h1_des))
    h2_des = min(hi_lim, max(lo_lim, h2_des))

    fast = False
    lim = 0.05
    if t_now - last_tg < 30.0:
        lim = 0.08
        fast = True

    dh1s = h1_des - h1_cur
    dh2s = h2_des - h2_cur
    if dh1s > lim:
        dh1s = lim
    if dh1s < -lim:
        dh1s = -lim
    if dh2s > lim:
        dh2s = lim
    if dh2s < -lim:
        dh2s = -lim
    if abs(dh1s) < 0.004:
        dh1s = 0.0
    if abs(dh2s) < 0.004:
        dh2s = 0.0

    h1_new = min(hi_lim, max(lo_lim, h1_cur + dh1s))
    h2_new = min(hi_lim, max(lo_lim, h2_cur + dh2s))
    h1_new = min(1.5, max(0.02, h1_new))
    h2_new = min(1.5, max(0.02, h2_new))

    if fast:
        diag = "production target changed: moving quickly on the constant-Q split"
    else:
        diag = "slope-corrected mass-balance load estimate; constrained constant-Q split with pump and upper-level margins"
    if abs(dh1s) < 1.0e-12 and abs(dh2s) < 1.0e-12:
        diag = diag + "; holding"

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"h1": h1_new, "h2": h2_new},
    }
