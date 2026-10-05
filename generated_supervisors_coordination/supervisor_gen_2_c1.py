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

    # times of last own setpoint change / target change
    last_change = -1.0e9
    last_tg = -1.0e9
    for i in range(1, n):
        c = W[i]
        p = W[i - 1]
        if abs(c["sp_h1"] - p["sp_h1"]) > 1.0e-7 or abs(c["sp_h2"] - p["sp_h2"]) > 1.0e-7:
            last_change = c["time"]
        if abs(c["production_target"] - p["production_target"]) > 1.0e-7:
            last_tg = c["time"]

    h1_cur = min(hi_lim, max(lo_lim, active_setpoints["h1"]))
    h2_cur = min(hi_lim, max(lo_lim, active_setpoints["h2"]))

    # ---- robust disturbance / gain estimate over recent quasi-steady samples ----
    sp1 = last["sp_h1"]
    sp2 = last["sp_h2"]
    t_lo = t_now - 240.0
    sd1 = 0.0
    sd2 = 0.0
    nd = 0
    sk1 = 0.0
    nk1 = 0
    sk2 = 0.0
    nk2 = 0
    for i in range(n):
        s = W[i]
        if s["time"] < t_lo:
            continue
        if abs(s["sp_h1"] - sp1) > 1.0e-6 or abs(s["sp_h2"] - sp2) > 1.0e-6:
            continue
        if i >= 1:
            p = W[i - 1]
            if abs(s["h1"] - p["h1"]) > 0.002 or abs(s["h2"] - p["h2"]) > 0.002:
                continue
            if abs(s["h3"] - p["h3"]) > 0.002 or abs(s["h4"] - p["h4"]) > 0.002:
                continue
        if s["v1"] < 2.0 or s["v1"] > 11.5 or s["v2"] < 2.0 or s["v2"] > 11.5:
            continue
        q1 = qh(s["h1"], a1)
        q2 = qh(s["h2"], a2)
        f3 = qh(s["h3"], a3)
        f4 = qh(s["h4"], a4)
        B = f3 / (1.0 - gam2)
        A = f4 / (1.0 - gam1)
        sd1 += q1 - (gam1 * A + (1.0 - gam2) * B)
        sd2 += q2 - ((1.0 - gam1) * A + gam2 * B)
        nd += 1
        if s["v1"] > 3.0:
            sk1 += A / s["v1"]
            nk1 += 1
        if s["v2"] > 3.0:
            sk2 += B / s["v2"]
            nk2 += 1

    if nd > 0:
        d1 = sd1 / nd
        d2 = sd2 / nd
    else:
        d1 = 0.0
        d2 = 0.0
    dc = 0.006
    if d1 > dc:
        d1 = dc
    if d1 < -dc:
        d1 = -dc
    if d2 > dc:
        d2 = dc
    if d2 < -dc:
        d2 = -dc

    k1e = k1n
    k2e = k2n
    if nk1 >= 5:
        k1e = sk1 / nk1
    if nk2 >= 5:
        k2e = sk2 / nk2
    if k1e > 1.05 * k1n:
        k1e = 1.05 * k1n
    if k1e < 0.65 * k1n:
        k1e = 0.65 * k1n
    if k2e > 1.05 * k2n:
        k2e = 1.05 * k2n
    if k2e < 0.65 * k2n:
        k2e = 0.65 * k2n

    # ---- feasible q1 interval from safety limits and h2 band ----
    h1_min = max(0.02, lo_lim)
    h1_max = min(1.5, hi_lim)
    h2_min = max(0.02, lo_lim, h2_lo)
    h2_max = min(1.5, hi_lim, h2_hi)
    lo_b = max(qh(h1_min, a1), Q - qh(h2_max, a2))
    hi_b = min(qh(h1_max, a1), Q - qh(h2_min, a2))
    if lo_b > hi_b:
        mid = 0.5 * (lo_b + hi_b)
        lo_b = mid
        hi_b = mid

    def predict(q1):
        q2 = Q - q1
        Q1 = q1 - d1
        Q2 = q2 - d2
        Bp = (4.0 * Q1 - Q2) / 3.0
        Ap = (4.0 * Q2 - Q1) / 3.0
        if Ap <= 0.0:
            v1p = 1.0e6
            h4p = -1.0
        else:
            v1p = Ap / k1e
            h4p = hq(0.8 * Ap, a4)
        if Bp <= 0.0:
            v2p = 1.0e6
            h3p = -1.0
        else:
            v2p = Bp / k2e
            h3p = hq(0.8 * Bp, a3)
        return q2, h3p, h4p, v1p, v2p

    def cost(q1, h1_ref, h2_ref):
        q2, h3p, h4p, v1p, v2p = predict(q1)
        h1p = hq(q1, a1)
        h2p = hq(q2, a2)
        c = 0.0
        if h3p > 0.0 and h3p > (ulim - 0.03):
            c += 6000.0 * (h3p - (ulim - 0.03))
        if h4p > 0.0 and h4p > (ulim - 0.03):
            c += 6000.0 * (h4p - (ulim - 0.03))
        if h2p < h2_lo:
            c += 6000.0 * (h2_lo - h2p)
        if h2p > h2_hi:
            c += 6000.0 * (h2p - h2_hi)
        if v1p > 11.5:
            c += 2000.0 * (v1p - 11.5)
        if v2p > 11.5:
            c += 2000.0 * (v2p - 11.5)
        if v1p < 1.5:
            c += 2000.0 * (1.5 - v1p)
        if v2p < 1.5:
            c += 2000.0 * (1.5 - v2p)
        c += 300.0 * (abs(h1p - h1_ref) + abs(h2p - h2_ref))
        return c

    q1_cur = qh(h1_cur, a1)
    q2_cur = qh(h2_cur, a2)
    Q_cur = q1_cur + q2_cur

    # hold through our own setpoint transient
    if (t_now - last_change) < 50.0 and last_change > last_tg:
        return {
            "diagnosis": "holding through own setpoint transient",
            "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur},
        }

    # on target and feasible -> hold (no travel)
    if abs(Q_cur - Q) < 0.0002:
        if cost(q1_cur, h1_cur, h2_cur) < 10.0:
            return {
                "diagnosis": "on target and constraints feasible: holding setpoints",
                "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur},
            }

    # search best setpoint pair on the constant-Q curve
    K = 80
    cand = []
    if hi_b - lo_b < 1.0e-12:
        cand.append(lo_b)
    else:
        for k in range(K + 1):
            cand.append(lo_b + (hi_b - lo_b) * k / K)
    qc = q1_cur
    if qc < lo_b:
        qc = lo_b
    if qc > hi_b:
        qc = hi_b
    cand.append(qc)

    best_q1 = qc
    best_c = None
    for q1 in cand:
        c = cost(q1, h1_cur, h2_cur)
        if best_c is None or c < best_c - 1.0e-9:
            best_c = c
            best_q1 = q1

    h1_des = hq(best_q1, a1)
    h2_des = hq(Q - best_q1, a2)
    if h1_des > hi_lim:
        h1_des = hi_lim
    if h1_des < lo_lim:
        h1_des = lo_lim
    if h2_des > hi_lim:
        h2_des = hi_lim
    if h2_des < lo_lim:
        h2_des = lo_lim

    # dead-band: ignore tiny moves
    if abs(h1_des - h1_cur) + abs(h2_des - h2_cur) < 0.008:
        return {
            "diagnosis": "within dead-band: holding setpoints",
            "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur},
        }

    # rate limit (faster on a fresh target change or an active violation)
    viol = False
    if last["h3"] > ulim - 0.02 or last["h4"] > ulim - 0.02:
        viol = True
    if last["v1"] > 11.6 or last["v2"] > 11.6:
        viol = True
    if last["h2"] < h2_lo - 0.005 or last["h2"] > h2_hi + 0.005:
        viol = True

    step = 0.04
    if (t_now - last_tg) < 150.0 and last_tg > last_change:
        step = 0.12
    if viol:
        if step < 0.07:
            step = 0.07

    if h1_des - h1_cur > step:
        h1_des = h1_cur + step
    elif h1_cur - h1_des > step:
        h1_des = h1_cur - step
    if h2_des - h2_cur > step:
        h2_des = h2_cur + step
    elif h2_cur - h2_des > step:
        h2_des = h2_cur - step

    return {
        "diagnosis": "filtered model-based split: move only when a predicted constraint needs it",
        "adjusted_setpoints": {"h1": h1_des, "h2": h2_des},
    }
