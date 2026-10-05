def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    S2 = (2.0 * g) ** 0.5
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1n = 0.00085
    k2n = 0.00095
    gam1 = 0.20
    gam2 = 0.20
    vmax = 12.0
    vmin = 1.0

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

    h1_cur = min(hi_lim, max(lo_lim, active_setpoints["h1"]))
    h2_cur = min(hi_lim, max(lo_lim, active_setpoints["h2"]))

    if n < 2:
        return {"diagnosis": "insufficient data",
                "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur}}

    M = 150
    i0 = n - M
    if i0 < 0:
        i0 = 0
    d1s = []
    d2s = []
    r1s = []
    r2s = []
    i = i0
    while i < n:
        s = W[i]
        q1 = qh(s["h1"], a1)
        q2 = qh(s["h2"], a2)
        F3 = qh(s["h3"], a3)
        F4 = qh(s["h4"], a4)
        inflow1 = F3 + (gam1 / (1.0 - gam1)) * F4
        inflow2 = F4 + (gam2 / (1.0 - gam2)) * F3
        d1s.append(q1 - inflow1)
        d2s.append(q2 - inflow2)
        if s["v1"] > 1.5:
            r1s.append(F4 / ((1.0 - gam1) * s["v1"]))
        if s["v2"] > 1.5:
            r2s.append(F3 / ((1.0 - gam2) * s["v2"]))
        i += 1

    d1_eff = min(d1s)
    d2_eff = sum(d2s) / len(d2s)
    if d1_eff < -0.004:
        d1_eff = -0.004
    if d1_eff > 0.001:
        d1_eff = 0.001
    if d2_eff < -0.004:
        d2_eff = -0.004
    if d2_eff > 0.004:
        d2_eff = 0.004

    def med(lst, fb):
        if not lst:
            return fb
        L = sorted(lst)
        return L[len(L) // 2]

    k1e = med(r1s, k1n)
    k2e = med(r2s, k2n)
    if k1e > k1n:
        k1e = k1n
    if k2e > k2n:
        k2e = k2n
    if k1e < 0.4 * k1n:
        k1e = 0.4 * k1n
    if k2e < 0.4 * k2n:
        k2e = 0.4 * k2n

    q1_min = qh(max(0.02, lo_lim), a1)
    q1_max = qh(min(1.5, hi_lim), a1)
    q2_min = qh(max(0.02, lo_lim), a2)
    q2_max = qh(min(1.5, hi_lim), a2)
    lo_b = max(q1_min, Q - q2_max)
    hi_b = min(q1_max, Q - q2_min)
    if lo_b > hi_b:
        mid = 0.5 * (lo_b + hi_b)
        lo_b = mid
        hi_b = mid

    H3t = ulim - 0.03
    H4t = ulim - 0.03
    h2_lo_t = h2_lo + 0.015
    h2_hi_t = h2_hi - 0.015

    q1_cur = qh(h1_cur, a1)
    if q1_cur < lo_b:
        q1_cur = lo_b
    if q1_cur > hi_b:
        q1_cur = hi_b

    K = 100
    best_q1 = q1_cur
    best_c = None
    k = 0
    while k <= K:
        if hi_b - lo_b < 1e-12:
            q1 = lo_b
        else:
            q1 = lo_b + (hi_b - lo_b) * k / K
        k += 1
        q2 = Q - q1
        if q1 <= 1e-7 or q2 <= 1e-7:
            continue
        Q1 = q1 - d1_eff
        Q2 = q2 - d2_eff
        F2 = (4.0 * Q1 - Q2) / 3.0
        F1 = (4.0 * Q2 - Q1) / 3.0
        if F2 <= 0.0 or F1 <= 0.0:
            continue
        h3p = (0.8 * F2 / a3) ** 2 / (2.0 * g)
        h4p = (0.8 * F1 / a4) ** 2 / (2.0 * g)
        h1p = hq(q1, a1)
        h2p = hq(q2, a2)
        v2p = F2 / k2e
        v1p = F1 / k1e
        c = 0.0
        if h3p > H3t:
            c += 4000.0 * (h3p - H3t)
        if h4p > H4t:
            c += 4000.0 * (h4p - H4t)
        if h2p < h2_lo_t:
            c += 4000.0 * (h2_lo_t - h2p)
        if h2p > h2_hi_t:
            c += 4000.0 * (h2p - h2_hi_t)
        if v2p > vmax:
            c += 3000.0 * (v2p - vmax)
        if v1p > vmax:
            c += 3000.0 * (v1p - vmax)
        if v2p < vmin:
            c += 3000.0 * (vmin - v2p)
        if v1p < vmin:
            c += 3000.0 * (vmin - v1p)
        c += 300.0 * (abs(h1p - h1_cur) + abs(h2p - h2_cur))
        if best_c is None or c < best_c:
            best_c = c
            best_q1 = q1

    h1_des = hq(best_q1, a1)
    h2_des = hq(Q - best_q1, a2)
    h1_des = min(hi_lim, max(lo_lim, h1_des))
    h2_des = min(hi_lim, max(lo_lim, h2_des))

    lim_step = 0.06
    if h1_des - h1_cur > lim_step:
        h1_des = h1_cur + lim_step
    elif h1_cur - h1_des > lim_step:
        h1_des = h1_cur - lim_step
    if h2_des - h2_cur > lim_step:
        h2_des = h2_cur + lim_step
    elif h2_cur - h2_des > lim_step:
        h2_des = h2_cur - lim_step

    last_change = -1.0e9
    last_tg = -1.0e9
    i = 1
    while i < n:
        c = W[i]
        p = W[i - 1]
        if abs(c["sp_h1"] - p["sp_h1"]) > 1e-9 or abs(c["sp_h2"] - p["sp_h2"]) > 1e-9:
            last_change = c["time"]
        if abs(c["production_target"] - p["production_target"]) > 1e-9:
            last_tg = c["time"]
        i += 1
    if (t_now - last_change) < 20.0 and last_change > last_tg:
        return {
            "diagnosis": "holding briefly through own setpoint transient",
            "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur},
        }

    return {
        "diagnosis": "constant-production split from windowed draw (min d1) and mean feed bias (d2); protects h3/h4, h2 band and pump limits",
        "adjusted_setpoints": {"h1": h1_des, "h2": h2_des},
    }
