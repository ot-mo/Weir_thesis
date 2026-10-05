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
    vmin = 1.0
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
    for i in range(1, n):
        c = W[i]
        p = W[i - 1]
        if abs(c["sp_h1"] - p["sp_h1"]) > 1.0e-9 or abs(c["sp_h2"] - p["sp_h2"]) > 1.0e-9:
            last_change = c["time"]
        if abs(c["production_target"] - p["production_target"]) > 1.0e-9:
            last_tg = c["time"]

    h1_cur = min(hi_lim, max(lo_lim, active_setpoints["h1"]))
    h2_cur = min(hi_lim, max(lo_lim, active_setpoints["h2"]))

    def d_est(idx, L):
        j = idx - L
        if j < 0:
            j = 0
        dt = W[idx]["time"] - W[j]["time"]
        if dt <= 0.0:
            return (0.0, 0.0)
        e1 = (W[idx]["h1"] - W[j]["h1"]) / dt
        e2 = (W[idx]["h2"] - W[j]["h2"]) / dt
        e3 = (W[idx]["h3"] - W[j]["h3"]) / dt
        e4 = (W[idx]["h4"] - W[j]["h4"]) / dt
        ff3 = qh(W[idx]["h3"], a3)
        ff4 = qh(W[idx]["h4"], a4)
        qq1 = qh(W[idx]["h1"], a1)
        qq2 = qh(W[idx]["h2"], a2)
        Af = (e4 + ff4) / (1.0 - gam1)
        Bf = (e3 + ff3) / (1.0 - gam2)
        return (e1 + qq1 - gam1 * Af - ff3, e2 + qq2 - gam2 * Bf - ff4)

    Mpt = 8
    STEP = 10
    Lfd = 8
    s1 = 0.0
    s2 = 0.0
    cnt = 0
    for m in range(Mpt):
        idx = n - 1 - m * STEP
        if idx < Lfd:
            break
        dd = d_est(idx, Lfd)
        s1 += dd[0]
        s2 += dd[1]
        cnt += 1
    d1 = 0.0
    d2 = 0.0
    if cnt > 0:
        d1 = s1 / cnt
        d2 = s2 / cnt
    dmax = 0.008
    if d1 > dmax:
        d1 = dmax
    elif d1 < -dmax:
        d1 = -dmax
    if d2 > dmax:
        d2 = dmax
    elif d2 < -dmax:
        d2 = -dmax

    k1e = k1n
    if last["v1"] > 0.5:
        est = qh(last["h4"], a4) / ((1.0 - gam1) * last["v1"])
        if est < k1e:
            k1e = est
    if k1e < 0.4 * k1n:
        k1e = 0.4 * k1n
    k2e = k2n
    if last["v2"] > 0.5:
        est = qh(last["h3"], a3) / ((1.0 - gam2) * last["v2"])
        if est < k2e:
            k2e = est
    if k2e < 0.4 * k2n:
        k2e = 0.4 * k2n

    q1_cur = qh(h1_cur, a1)
    h1_min = max(0.02, lo_lim)
    h1_max = min(1.5, hi_lim)
    q1_min_lim = qh(h1_min, a1)
    q1_max_lim = qh(h1_max, a1)
    q2_min_lim = qh(max(0.02, lo_lim), a2)
    q2_max_lim = qh(min(1.5, hi_lim), a2)
    lo_b = max(q1_min_lim, Q - q2_max_lim)
    hi_b = min(q1_max_lim, Q - q2_min_lim)
    if lo_b > hi_b:
        mid = 0.5 * (lo_b + hi_b)
        lo_b = mid
        hi_b = mid

    H3t = ulim - 0.05
    H4t = ulim - 0.05
    if H3t < 0.05:
        H3t = 0.05
    if H4t < 0.05:
        H4t = 0.05
    h2hi_t = h2_hi - 0.01
    h2lo_t = h2_lo + 0.01
    vhi_t = vmax - 1.2
    vlo_t = vmin + 0.5

    if q1_cur < lo_b:
        q1_cur = lo_b
    if q1_cur > hi_b:
        q1_cur = hi_b

    cand = []
    K = 80
    if hi_b - lo_b < 1.0e-9:
        cand.append(lo_b)
    else:
        for k in range(K + 1):
            cand.append(lo_b + (hi_b - lo_b) * k / K)
    cand.append(q1_cur)

    best_q1 = q1_cur
    best_c = None
    for q1 in cand:
        q2 = Q - q1
        if q1 <= 1.0e-7 or q2 <= 1.0e-7:
            continue
        u1 = q1 - d1
        u2 = q2 - d2
        Bp = (4.0 * u1 - u2) / 3.0
        Ap = (4.0 * u2 - u1) / 3.0
        if Bp <= 0.0 or Ap <= 0.0:
            continue
        h3p = (0.8 * Bp / a3) ** 2 / (2.0 * g)
        h4p = (0.8 * Ap / a4) ** 2 / (2.0 * g)
        h1p = hq(q1, a1)
        h2p = hq(q2, a2)
        v2p = Bp / k2e
        v1p = Ap / k1e
        c = 0.0
        if h3p > H3t:
            c += 4000.0 * (h3p - H3t)
        if h4p > H4t:
            c += 4000.0 * (h4p - H4t)
        if h2p > h2hi_t:
            c += 1500.0 * (h2p - h2hi_t)
        if h2p < h2lo_t:
            c += 1500.0 * (h2lo_t - h2p)
        if v2p > vhi_t:
            c += 2500.0 * (v2p - vhi_t)
        if v1p > vhi_t:
            c += 2500.0 * (v1p - vhi_t)
        if v2p < vlo_t:
            c += 2500.0 * (vlo_t - v2p)
        if v1p < vlo_t:
            c += 2500.0 * (vlo_t - v1p)
        c += 120.0 * (abs(h1p - h1_cur) + abs(h2p - h2_cur))
        if best_c is None or c < best_c:
            best_c = c
            best_q1 = q1

    h1_des = hq(best_q1, a1)
    h2_des = hq(Q - best_q1, a2)
    h1_des = min(hi_lim, max(lo_lim, h1_des))
    h2_des = min(hi_lim, max(lo_lim, h2_des))

    if abs(h1_des - h1_cur) < 0.005 and abs(h2_des - h2_cur) < 0.005:
        h1_des = h1_cur
        h2_des = h2_cur

    lim_step = 0.06
    if h1_des - h1_cur > lim_step:
        h1_des = h1_cur + lim_step
    elif h1_cur - h1_des > lim_step:
        h1_des = h1_cur - lim_step
    if h2_des - h2_cur > lim_step:
        h2_des = h2_cur + lim_step
    elif h2_cur - h2_des > lim_step:
        h2_des = h2_cur - lim_step

    tight = False
    if last["h3"] > ulim - 0.06 or last["h4"] > ulim - 0.06:
        tight = True
    if last["h2"] > h2_hi - 0.015 or last["h2"] < h2_lo + 0.015:
        tight = True
    if last["v1"] > vmax - 0.4 or last["v2"] > vmax - 0.4:
        tight = True

    since_sp = t_now - last_change
    if since_sp < 12.0 and last_change > last_tg and not tight:
        return {
            "diagnosis": "holding through own recent setpoint move; no active constraint threat",
            "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur},
        }

    return {
        "diagnosis": "low-passed exact mass-balance disturbance estimate; min-travel split on constant-Q curve keeps h3/h4 and pump voltages inside limits",
        "adjusted_setpoints": {"h1": h1_des, "h2": h2_des},
    }
