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

    # pump-flow estimates for the gain check include the measured upper-tank
    # accumulation, so a transient fill/drain of tank3/tank4 is not misread as
    # a pump-gain loss (the load estimate d1,d2 above is unchanged).
    j0 = n - 11
    if j0 < 0:
        j0 = 0
    span = (n - 1) - j0
    r4 = 0.0
    r3 = 0.0
    if span > 0:
        r4 = (last["h4"] - W[j0]["h4"]) / float(span)
        r3 = (last["h3"] - W[j0]["h3"]) / float(span)
    Amd = (f4 + r4) / (1.0 - gam1)
    Bmd = (f3 + r3) / (1.0 - gam2)
    if Amd < 0.0:
        Amd = 0.0
    if Bmd < 0.0:
        Bmd = 0.0

    k1e = k1n
    if last["v1"] > 0.5:
        tmp = Amd / last["v1"]
        if tmp < k1e:
            k1e = tmp
        if k1e < 0.5 * k1n:
            k1e = 0.5 * k1n
    k2e = k2n
    if last["v2"] > 0.5:
        tmp = Bmd / last["v2"]
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
    best_Bp = None
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
            best_Bp = Bp

    h1_des = hq(best_q1, a1)
    h2_des = hq(Q - best_q1, a2)
    h1_des = min(hi_lim, max(lo_lim, h1_des))
    h2_des = min(hi_lim, max(lo_lim, h2_des))

    # CHANGED: pump-saturation relief on the split.  Pump 1 is the actuator of
    # the h2 loop and pump 2 of the h1 loop, so a loop whose pump sits on its
    # voltage ceiling while its own lower-tank level is still short of the
    # commanded setpoint and not rising cannot get there at the present load:
    # the commanded split is not achievable, and both the level and the
    # production suffer until the ~90 s-lagged load estimate finally moves.
    # The clamped voltage is an immediate indicator, so shift 0.5 L/s of
    # production off that pump's tank (total target production preserved) and
    # reject the shift if the model says the shifted pair would push tank3 or
    # tank4 over the limit.  The level-error and non-rising-level guards keep
    # the supervisor's own setpoint transient from firing it.
    j20 = n - 1 - 20
    if j20 < 0:
        j20 = 0
    sp20 = (n - 1) - j20
    sl2 = 0.0
    sl1 = 0.0
    if sp20 > 0:
        sl2 = (last["h2"] - W[j20]["h2"]) / float(sp20)
        sl1 = (last["h1"] - W[j20]["h1"]) / float(sp20)
    sat_shift = 0.0
    if last["v1"] > vmax - 0.15 and last["h2"] < h2_des - 0.02 and sl2 < 1.0e-5:
        sat_shift = 5.0e-4
    elif last["v2"] > vmax - 0.15 and last["h1"] < h1_des - 0.02 and sl1 < 1.0e-5:
        sat_shift = -5.0e-4
    sat_msg = ""
    if sat_shift != 0.0:
        q1s = best_q1 + sat_shift
        q2s = Q - best_q1 - sat_shift
        if q1s > 1.0e-6 and q2s > 1.0e-6:
            h1s = hq(q1s, a1)
            h2s = hq(q2s, a2)
            h2s = min(h2_hi, max(h2_lo, h2s))
            h1s = min(hi_lim, max(lo_lim, h1s))
            Q1s = qh(h1s, a1) - d1
            Q2s = qh(h2s, a2) - d2
            Bs = (4.0 * Q1s - Q2s) / 3.0
            As = (4.0 * Q2s - Q1s) / 3.0
            h3s = 0.0
            h4s = 0.0
            if Bs > 0.0:
                h3s = (0.8 * Bs / a3) ** 2 / (2.0 * g)
            if As > 0.0:
                h4s = (0.8 * As / a4) ** 2 / (2.0 * g)
            if h3s < ulim - 0.05 and h4s < ulim - 0.05:
                h1_des = h1s
                h2_des = h2s
                if sat_shift > 0.0:
                    sat_msg = "pump1 at voltage ceiling with h2 short of setpoint: shifted production to tank1"
                else:
                    sat_msg = "pump2 at voltage ceiling with h1 short of setpoint: shifted production to tank2"

    lim_step = 0.06
    if h1_des - h1_cur > lim_step:
        h1_des = h1_cur + lim_step
    elif h1_cur - h1_des > lim_step:
        h1_des = h1_cur - lim_step
    if h2_des - h2_cur > lim_step:
        h2_des = h2_cur + lim_step
    elif h2_cur - h2_des > lim_step:
        h2_des = h2_cur - lim_step

    # lag-compensated (PD) production-error trim on the tank-1 setpoint
    Qmeas = last["production"] * 0.001
    eq = Q - Qmeas
    j_eq = n - 1 - 90
    if j_eq < 0:
        j_eq = 0
    span_eq = (n - 1) - j_eq
    if span_eq > 0:
        eq_past = Q - W[j_eq]["production"] * 0.001
        eq_pred = eq + 80.0 * (eq - eq_past) / float(span_eq)
    else:
        eq_pred = eq
    if eq > 0.0:
        if eq_pred < 0.0:
            eq_pred = 0.0
    elif eq < 0.0:
        if eq_pred > 0.0:
            eq_pred = 0.0
    if eq_pred > 2.5e-3:
        eq_pred = 2.5e-3
    if eq_pred < -2.5e-3:
        eq_pred = -2.5e-3
    if eq_pred > 1.5e-4 or eq_pred < -1.5e-4:
        dq1 = 0.30 * eq_pred
        if dq1 > 4.0e-4:
            dq1 = 4.0e-4
        if dq1 < -4.0e-4:
            dq1 = -4.0e-4
        if dq1 > 0.0:
            Bmax = a3 * ((2.0 * g * (ulim - 0.10)) ** 0.5) / 0.8
            Bcur = a3 * ((2.0 * g * last["h3"]) ** 0.5) / 0.8
            if best_Bp is not None and best_Bp > Bcur:
                Bcur = best_Bp
            room = (Bmax - Bcur) / (4.0 / 3.0)
            if room < 0.0:
                room = 0.0
            if dq1 > room:
                dq1 = room
        if abs(dq1) > 1.0e-7 and h1_des > 1.0e-6:
            hs = a1 * g / ((2.0 * g * h1_des) ** 0.5)
            if hs > 1.0e-9:
                dh = dq1 / hs
                if dh > 0.02:
                    dh = 0.02
                if dh < -0.02:
                    dh = -0.02
                h1_des = min(hi_lim, max(lo_lim, h1_des + dh))

    since_sp = t_now - last_change
    if since_sp < 45.0 and last_change > last_tg:
        return {
            "diagnosis": "holding during own setpoint transient before re-evaluating constraints",
            "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur},
        }

    diag = "model split from upper-level load plus lag-compensated (predicted) production trim on h1, bounded by tank-3/pump-2 headroom"
    if sat_msg != "":
        diag = sat_msg + "; " + diag
    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"h1": h1_des, "h2": h2_des},
    }
