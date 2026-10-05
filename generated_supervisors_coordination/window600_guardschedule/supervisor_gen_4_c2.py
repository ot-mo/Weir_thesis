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
    if n == 0:
        return {"diagnosis": "no data", "adjusted_setpoints": {"h1": 0.3, "h2": 0.35}}
    last = W[n - 1]

    Q_tgt_L = objectives["production_target"]
    Q_tgt = Q_tgt_L / 1000.0
    h2_lo = objectives["h2_band"][0]
    h2_hi = objectives["h2_band"][1]
    ulim = objectives["upper_level_limit"]
    lo_lim = objectives["setpoint_limits"][0]
    hi_lim = objectives["setpoint_limits"][1]

    def qh(h, a):
        if h <= 0.0:
            return 0.0
        return a * ((2.0 * g * h) ** 0.5)

    def hq(q, a):
        if q <= 0.0:
            return 0.0
        r = q / (a * S2)
        return r * r

    d1_vals = []
    d2_vals = []
    k1_vals = []
    k2_vals = []
    for i in range(1, n):
        prev = W[i - 1]
        cur = W[i]
        dh1 = cur["h1"] - prev["h1"]
        dh2 = cur["h2"] - prev["h2"]
        dh3 = cur["h3"] - prev["h3"]
        dh4 = cur["h4"] - prev["h4"]
        h1 = cur["h1"]
        h2 = cur["h2"]
        h3 = cur["h3"]
        h4 = cur["h4"]
        f1 = a1 * ((2.0 * g * max(0.0, h1)) ** 0.5)
        f2 = a2 * ((2.0 * g * max(0.0, h2)) ** 0.5)
        f3 = a3 * ((2.0 * g * max(0.0, h3)) ** 0.5)
        f4 = a4 * ((2.0 * g * max(0.0, h4)) ** 0.5)
        A = (dh4 + f4) / (1.0 - gam1)
        B = (dh3 + f3) / (1.0 - gam2)
        d1 = dh1 + f1 - f3 - gam1 * A
        d2 = dh2 + f2 - f4 - gam2 * B
        d1_vals.append(d1)
        d2_vals.append(d2)
        v1 = cur["v1"]
        v2 = cur["v2"]
        if v1 > 1.0 and A > 0.0:
            k1_vals.append(A / v1)
        if v2 > 1.0 and B > 0.0:
            k2_vals.append(B / v2)

    if d1_vals:
        d1_min = min(d1_vals)
        d1_max = max(d1_vals)
        d2_min = min(d2_vals)
        d2_max = max(d2_vals)
    else:
        d1_min = d1_max = d2_min = d2_max = 0.0

    k1_min = k1n
    if k1_vals:
        k1_min = min(k1_vals)
        if k1_min < 0.5 * k1n:
            k1_min = 0.5 * k1n
        if k1_min > k1n:
            k1_min = k1n
    k2_min = k2n
    if k2_vals:
        k2_min = min(k2_vals)
        if k2_min < 0.5 * k2n:
            k2_min = 0.5 * k2n
        if k2_min > k2n:
            k2_min = k2n

    h1_cur = min(hi_lim, max(lo_lim, active_setpoints["h1"]))
    h2_cur = min(hi_lim, max(lo_lim, active_setpoints["h2"]))

    h1_min = max(0.02, lo_lim)
    h1_max = min(1.5, hi_lim)
    h2_min = max(0.02, lo_lim)
    h2_max = min(1.5, hi_lim)

    H3_lim = ulim - 0.03
    H4_lim = ulim - 0.03
    v_lim = vmax - 0.2

    best = [None, h1_cur, h2_cur]

    def eval_point(h1, h2):
        q1 = qh(h1, a1)
        q2 = qh(h2, a2)
        Q_act = q1 + q2
        prod_err = abs(Q_act - Q_tgt)
        Q1_3 = q1 - d1_min
        Q2_3 = q2 - d2_max
        B_max = (4.0 * Q1_3 - Q2_3) / 3.0
        if B_max < 0.0:
            B_max = 0.0
        h3_max = ((1.0 - gam2) * B_max / a3) ** 2 / (2.0 * g)
        Q2_4 = q2 - d2_min
        Q1_4 = q1 - d1_max
        A_max = (4.0 * Q2_4 - Q1_4) / 3.0
        if A_max < 0.0:
            A_max = 0.0
        h4_max = ((1.0 - gam1) * A_max / a4) ** 2 / (2.0 * g)
        v2_max = B_max / k2_min if k2_min > 0 else 1e9
        v1_max = A_max / k1_min if k1_min > 0 else 1e9

        cost = 0.0
        cost += prod_err
        if h2 < h2_lo:
            cost += 1000.0 + 100.0 * (h2_lo - h2)
        elif h2 > h2_hi:
            cost += 1000.0 + 100.0 * (h2 - h2_hi)
        if h3_max > H3_lim:
            cost += 1000.0 + 100.0 * (h3_max - H3_lim)
        if h4_max > H4_lim:
            cost += 1000.0 + 100.0 * (h4_max - H4_lim)
        if v1_max > v_lim:
            cost += 1000.0 + 100.0 * (v1_max - v_lim)
        if v2_max > v_lim:
            cost += 1000.0 + 100.0 * (v2_max - v_lim)
        if h1 < 0.02:
            cost += 5000.0 + 500.0 * (0.02 - h1)
        if h1 > 1.5:
            cost += 5000.0 + 500.0 * (h1 - 1.5)
        if h2 < 0.02:
            cost += 5000.0 + 500.0 * (0.02 - h2)
        if h2 > 1.5:
            cost += 5000.0 + 500.0 * (h2 - 1.5)
        cost += 50.0 * (abs(h1 - h1_cur) + abs(h2 - h2_cur))
        return cost

    def search(h1_lo, h1_hi, h2_lo, h2_hi, N):
        if h1_hi <= h1_lo or h2_hi <= h2_lo:
            return
        for i in range(N + 1):
            h1 = h1_lo + (h1_hi - h1_lo) * i / N
            for j in range(N + 1):
                h2 = h2_lo + (h2_hi - h2_lo) * j / N
                c = eval_point(h1, h2)
                if best[0] is None or c < best[0]:
                    best[0] = c
                    best[1] = h1
                    best[2] = h2

    search(h1_min, h1_max, h2_min, h2_max, 30)
    h1_span = (h1_max - h1_min) / 30.0
    h2_span = (h2_max - h2_min) / 30.0
    search(max(h1_min, best[1] - h1_span), min(h1_max, best[1] + h1_span),
           max(h2_min, best[2] - h2_span), min(h2_max, best[2] + h2_span), 30)
    h1_span2 = h1_span / 30.0
    h2_span2 = h2_span / 30.0
    search(max(h1_min, best[1] - h1_span2), min(h1_max, best[1] + h1_span2),
           max(h2_min, best[2] - h2_span2), min(h2_max, best[2] + h2_span2), 20)

    h1_des = best[1]
    h2_des = best[2]

    lim_step = 0.08
    if h1_des - h1_cur > lim_step:
        h1_des = h1_cur + lim_step
    elif h1_cur - h1_des > lim_step:
        h1_des = h1_cur - lim_step
    if h2_des - h2_cur > lim_step:
        h2_des = h2_cur + lim_step
    elif h2_cur - h2_des > lim_step:
        h2_des = h2_cur - lim_step

    h1_des = min(hi_lim, max(lo_lim, h1_des))
    h2_des = min(hi_lim, max(lo_lim, h2_des))

    return {
        "diagnosis": "robust worst-case split using window min/max mass-balance load; prioritizes constraints and limits travel",
        "adjusted_setpoints": {"h1": h1_des, "h2": h2_des},
    }
