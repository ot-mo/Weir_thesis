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
        return (q / (a * S2)) ** 2

    def cl(x, lo, hi):
        if x < lo:
            return lo
        if x > hi:
            return hi
        return x

    h1_cur = cl(active_setpoints["h1"], lo_lim, hi_lim)
    h2_cur = cl(active_setpoints["h2"], lo_lim, hi_lim)

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

    # effective pump gains from the most recent quasi-steady upper tank level
    k1e = k1n
    k2e = k2n
    got1 = False
    got2 = False
    j = n - 1
    while j >= 16 and not (got1 and got2):
        c = W[j]
        p = W[j - 15]
        if (not got1) and c["v1"] > 2.5 and abs(c["h4"] - p["h4"]) < 0.003:
            vv = qh(c["h4"], a4) / ((1.0 - gam1) * c["v1"])
            if 0.35 * k1n <= vv <= 1.25 * k1n:
                k1e = vv
                got1 = True
        if (not got2) and c["v2"] > 2.5 and abs(c["h3"] - p["h3"]) < 0.003:
            vv = qh(c["h3"], a3) / ((1.0 - gam2) * c["v2"])
            if 0.35 * k2n <= vv <= 1.25 * k2n:
                k2e = vv
                got2 = True
        j -= 1

    # derivative-corrected mass-balance disturbance estimate
    sd1 = 0.0
    sd2 = 0.0
    cnt = 0
    j = n - 1
    jmin = n - 40
    if jmin < 20:
        jmin = 20
    while j >= jmin:
        c = W[j]
        p = W[j - 20]
        dt = c["time"] - p["time"]
        if dt > 0.0:
            dh1 = (c["h1"] - p["h1"]) / dt
            dh2 = (c["h2"] - p["h2"]) / dt
            sd1 += dh1 + qh(c["h1"], a1) - qh(c["h3"], a3) - gam1 * k1e * c["v1"]
            sd2 += dh2 + qh(c["h2"], a2) - qh(c["h4"], a4) - gam2 * k2e * c["v2"]
            cnt += 1
        j -= 1
    if cnt >= 5:
        d1 = sd1 / cnt
        d2 = sd2 / cnt
    else:
        c = last
        d1 = qh(c["h1"], a1) - qh(c["h3"], a3) - gam1 * k1e * c["v1"]
        d2 = qh(c["h2"], a2) - qh(c["h4"], a4) - gam2 * k2e * c["v2"]

    def predict(q1t, q2t):
        Q1 = q1t - d1
        Q2 = q2t - d2
        B = (4.0 * Q1 - Q2) / 3.0
        A = (4.0 * Q2 - Q1) / 3.0
        if A < 0.0:
            A = 0.0
        if B < 0.0:
            B = 0.0
        v1 = A / k1e
        v2 = B / k2e
        h1 = hq(q1t, a1)
        h2 = hq(q2t, a2)
        if v1 > vmax or v1 < vmin:
            A = k1e * (vmax if v1 > vmax else vmin)
            B = (q1t - gam1 * A - d1) / (1.0 - gam2)
            if B < 0.0:
                B = 0.0
            v2 = B / k2e
            if v2 > vmax or v2 < vmin:
                B = k2e * (vmax if v2 > vmax else vmin)
                v2 = B / k2e
                q1x = gam1 * A + (1.0 - gam2) * B + d1
                h1 = hq(q1x, a1)
            q2x = (1.0 - gam1) * A + gam2 * B + d2
            h2 = hq(q2x, a2)
        elif v2 > vmax or v2 < vmin:
            B = k2e * (vmax if v2 > vmax else vmin)
            A = (q2t - gam2 * B - d2) / (1.0 - gam1)
            if A < 0.0:
                A = 0.0
            v1 = A / k1e
            if v1 > vmax or v1 < vmin:
                A = k1e * (vmax if v1 > vmax else vmin)
                v1 = A / k1e
                q2x = (1.0 - gam1) * A + gam2 * B + d2
                h2 = hq(q2x, a2)
            q1x = gam1 * A + (1.0 - gam2) * B + d1
            h1 = hq(q1x, a1)
        h3 = (0.8 * B / a3) ** 2 / (2.0 * g)
        h4 = (0.8 * A / a4) ** 2 / (2.0 * g)
        return (h1, h2, h3, h4, v1, v2)

    H3T = ulim - 0.01

    def cost(q1t):
        q2t = Q - q1t
        if q1t <= 1.0e-6 or q2t <= 1.0e-6:
            return None
        st = predict(q1t, q2t)
        h1p = st[0]
        h2p = st[1]
        h3p = st[2]
        h4p = st[3]
        v1p = st[4]
        v2p = st[5]
        c = 150.0 * (abs(h1p - h1_cur) + abs(h2p - h2_cur))
        c += 1500.0 * abs((qh(h1p, a1) + qh(h2p, a2)) - Q) * 1000.0
        if h3p > H3T:
            c += 5000.0 * (h3p - H3T) + 3000.0
        if h4p > H3T:
            c += 5000.0 * (h4p - H3T) + 3000.0
        if h2p < h2_lo:
            c += 5000.0 * (h2_lo - h2p) + 3000.0
        if h2p > h2_hi:
            c += 5000.0 * (h2p - h2_hi) + 3000.0
        if h1p < 0.02 or h1p > 1.5:
            c += 8000.0
        if h2p < 0.02 or h2p > 1.5:
            c += 8000.0
        if v1p > 11.6:
            c += 300.0 * (v1p - 11.6)
        if v2p > 11.6:
            c += 300.0 * (v2p - 11.6)
        return c

    h1l = cl(0.02, lo_lim, 1.5)
    h2l = cl(0.02, lo_lim, 1.5)
    h1h = cl(1.5, lo_lim, 1.5)
    h2h = cl(1.5, lo_lim, 1.5)
    qlo = qh(h1l, a1)
    q2l = Q - qh(h2h, a2)
    if q2l > qlo:
        qlo = q2l
    qhi = qh(h1h, a1)
    q2h = Q - qh(h2l, a2)
    if q2h < qhi:
        qhi = q2h
    if qlo > qhi:
        mid = 0.5 * (qlo + qhi)
        qlo = mid
        qhi = mid
    if qhi > Q - 1.0e-6:
        qhi = Q - 1.0e-6
    if qlo < 1.0e-6:
        qlo = 1.0e-6

    q1_cur = qh(h1_cur, a1)

    best_q1 = q1_cur
    best_c = None
    K = 80
    if qhi - qlo < 1.0e-12:
        cands = [qlo]
    else:
        cands = []
        k = 0
        while k <= K:
            cands.append(qlo + (qhi - qlo) * k / K)
            k += 1
    cands.append(cl(q1_cur, qlo, qhi))
    for q1t in cands:
        cc = cost(q1t)
        if cc is None:
            continue
        if best_c is None or cc < best_c:
            best_c = cc
            best_q1 = q1t

    h1_new = cl(hq(best_q1, a1), lo_lim, hi_lim)
    h2_new = cl(hq(Q - best_q1, a2), lo_lim, hi_lim)

    st_cur = predict(qh(h1_cur, a1), qh(h2_cur, a2))
    Q_ach = qh(st_cur[0], a1) + qh(st_cur[1], a2)

    cons_ok = True
    if st_cur[2] > H3T or st_cur[3] > H3T:
        cons_ok = False
    if st_cur[1] < h2_lo + 0.005 or st_cur[1] > h2_hi - 0.005:
        cons_ok = False
    if st_cur[0] < 0.02 or st_cur[0] > 1.5:
        cons_ok = False
    if st_cur[1] < 0.02 or st_cur[1] > 1.5:
        cons_ok = False
    if last["h3"] > ulim - 0.005 or last["h4"] > ulim - 0.005:
        cons_ok = False
    if last["h2"] < h2_lo + 0.005 or last["h2"] > h2_hi - 0.005:
        cons_ok = False
    if abs(last["h1"] - h1_cur) > 0.02 or abs(last["h2"] - h2_cur) > 0.02:
        cons_ok = False

    since_change = t_now - last_change
    prod_err = abs(Q_ach - Q)

    if prod_err > 0.0003 and since_change > 30.0:
        return {
            "diagnosis": "predicted production off target: re-splitting along the constant-Q curve",
            "adjusted_setpoints": {"h1": h1_new, "h2": h2_new},
        }

    if cons_ok:
        return {
            "diagnosis": "production on target and h2/h3/h4 inside margins; holding setpoints",
            "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur},
        }

    if since_change < 70.0:
        return {
            "diagnosis": "holding while the previous setpoint change settles before re-checking constraints",
            "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur},
        }

    if abs(h1_new - h1_cur) < 0.004 and abs(h2_new - h2_cur) < 0.004:
        return {
            "diagnosis": "constraint pressure within model tolerance; no setpoint move needed",
            "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur},
        }

    return {
        "diagnosis": "disturbance threatens an upper level or the h2 band: re-splitting production along the constant-Q curve",
        "adjusted_setpoints": {"h1": h1_new, "h2": h2_new},
    }
