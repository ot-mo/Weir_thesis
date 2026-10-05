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
    i = 1
    while i < n:
        c = W[i]
        p = W[i - 1]
        if abs(c["sp_h1"] - p["sp_h1"]) > 1.0e-9 or abs(c["sp_h2"] - p["sp_h2"]) > 1.0e-9:
            last_change = c["time"]
        if abs(c["production_target"] - p["production_target"]) > 1.0e-9:
            last_tg = c["time"]
        i += 1

    h1_cur = min(hi_lim, max(lo_lim, active_setpoints["h1"]))
    h2_cur = min(hi_lim, max(lo_lim, active_setpoints["h2"]))

    q1m = qh(last["h1"], a1)
    q2m = qh(last["h2"], a2)
    f3 = qh(last["h3"], a3)
    f4 = qh(last["h4"], a4)
    Bm = f3 / (1.0 - gam2)
    Am = f4 / (1.0 - gam1)
    d1 = q1m - (gam1 * Am + (1.0 - gam2) * Bm)
    d2 = q2m - ((1.0 - gam1) * Am + gam2 * Bm)

    k1e = k1n
    if last["v1"] > 0.5:
        tmp = Am / last["v1"]
        if tmp < k1e:
            k1e = tmp
        if k1e < 0.5 * k1n:
            k1e = 0.5 * k1n
    k2e = k2n
    if last["v2"] > 0.5:
        tmp = Bm / last["v2"]
        if tmp < k2e:
            k2e = tmp
        if k2e < 0.5 * k2n:
            k2e = 0.5 * k2n

    q1n = qh(0.30, a1)
    q2n = qh(0.35, a2)
    ratio = q1n / (q1n + q2n)

    h1_min = max(0.02, lo_lim)
    h1_max = min(1.5, hi_lim)
    q1_min = qh(h1_min, a1)
    q1_max = qh(h1_max, a1)
    q2_min = qh(max(0.02, lo_lim), a2)
    q2_max = qh(min(1.5, hi_lim), a2)
    lo_b = max(q1_min, Q - q2_max)
    hi_b = min(q1_max, Q - q2_min)
    if lo_b > hi_b:
        mid = 0.5 * (lo_b + hi_b)
        lo_b = mid
        hi_b = mid

    cand = []
    K = 60
    if hi_b - lo_b < 1.0e-9:
        cand.append(lo_b)
    else:
        for k in range(K + 1):
            cand.append(lo_b + (hi_b - lo_b) * k / K)
    q1_cur = qh(h1_cur, a1)
    if q1_cur < lo_b:
        q1_cur = lo_b
    if q1_cur > hi_b:
        q1_cur = hi_b
    cand.append(q1_cur)

    H3t = ulim - 0.05
    H4t = ulim - 0.05

    best_q1 = q1_cur
    best_c = None
    for q1 in cand:
        q2 = Q - q1
        if q1 <= 1.0e-7 or q2 <= 1.0e-7:
            continue
        Q1 = q1 - d1
        Q2 = q2 - d2
        Bp = (4.0 * Q1 - Q2) / 3.0
        Ap = (4.0 * Q2 - Q1) / 3.0
        if Bp <= 0.0 or Ap <= 0.0:
            continue
        h3p = (0.8 * Bp / a3) ** 2 / (2.0 * g)
        h4p = (0.8 * Ap / a4) ** 2 / (2.0 * g)
        h1p = hq(q1, a1)
        h2p = hq(q2, a2)
        c = 0.0
        if h3p > H3t:
            c += 3000.0 * (h3p - H3t)
        if h4p > H4t:
            c += 3000.0 * (h4p - H4t)
        if h2p < h2_lo:
            c += 3000.0 * (h2_lo - h2p)
        if h2p > h2_hi:
            c += 3000.0 * (h2p - h2_hi)
        v2p = Bp / k2e
        v1p = Ap / k1e
        if v2p > vmax:
            c += 2000.0 * (v2p - vmax)
        if v1p > vmax:
            c += 2000.0 * (v1p - vmax)
        c += 200.0 * (abs(h1p - h1_cur) + abs(h2p - h2_cur))
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

    since_sp = t_now - last_change
    if since_sp < 45.0 and last_change > last_tg:
        return {
            "diagnosis": "holding during own setpoint transient before re-evaluating constraints",
            "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur},
        }

    return {
        "diagnosis": "model-based split: estimate load from upper levels, bias h1/h2 along the constant-Q curve to keep h3/h4 and pumps safe",
        "adjusted_setpoints": {"h1": h1_des, "h2": h2_des},
    }
