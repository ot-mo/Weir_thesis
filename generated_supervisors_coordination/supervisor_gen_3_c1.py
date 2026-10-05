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

    lo_lim = objectives['setpoint_limits'][0]
    hi_lim = objectives['setpoint_limits'][1]
    Qt = objectives['production_target'] / 1000.0
    h2_lo = objectives['h2_band'][0]
    h2_hi = objectives['h2_band'][1]
    ulim = objectives['upper_level_limit']

    h1_cur = min(hi_lim, max(lo_lim, active_setpoints['h1']))
    h2_cur = min(hi_lim, max(lo_lim, active_setpoints['h2']))

    def qh(h, a):
        if h <= 0.0:
            return 0.0
        return a * ((2.0 * g * h) ** 0.5)

    def hq(q, a):
        if q <= 0.0:
            return 0.0
        r = q / (a * S2)
        return r * r

    tc = -1.0e9
    tg = -1.0e9
    d1s = []
    d2s = []
    err2 = 0.0
    for i in range(n):
        s = W[i]
        if i > 0:
            p = W[i - 1]
            if abs(s['sp_h1'] - p['sp_h1']) > 1.0e-9 or abs(s['sp_h2'] - p['sp_h2']) > 1.0e-9:
                tc = s['time']
            if abs(s['production_target'] - p['production_target']) > 1.0e-9:
                tg = s['time']
        if (s['time'] - tc >= 60.0) and (s['time'] - tg >= 60.0):
            e = abs(s['h2'] - s['sp_h2'])
            if e > err2:
                err2 = e
        if s['time'] - tc < 75.0 or s['time'] - tg < 75.0:
            continue
        q1 = qh(s['h1'], a1)
        q2 = qh(s['h2'], a2)
        A = qh(s['h4'], a4) / (1.0 - gam1)
        B = qh(s['h3'], a3) / (1.0 - gam2)
        Av = k1n * s['v1']
        Bv = k2n * s['v2']
        if Av < A:
            A = Av
        if Bv < B:
            B = Bv
        d1s.append(q1 - (gam1 * A + (1.0 - gam2) * B))
        d2s.append(q2 - ((1.0 - gam1) * A + gam2 * B))

    if err2 > 0.09:
        err2 = 0.09

    A_last = qh(last['h4'], a4) / (1.0 - gam1)
    B_last = qh(last['h3'], a3) / (1.0 - gam2)
    Av = k1n * last['v1']
    Bv = k2n * last['v2']
    if Av < A_last:
        A_last = Av
    if Bv < B_last:
        B_last = Bv
    k1e = k1n
    k2e = k2n
    if last['v1'] > 2.0 and A_last > 1.0e-9:
        k1e = A_last / last['v1']
    if last['v2'] > 2.0 and B_last > 1.0e-9:
        k2e = B_last / last['v2']
    if k1e > k1n:
        k1e = k1n
    if k2e > k2n:
        k2e = k2n
    if k1e < 0.6 * k1n:
        k1e = 0.6 * k1n
    if k2e < 0.6 * k2n:
        k2e = 0.6 * k2n

    f1 = qh(last['h1'], a1) - (gam1 * A_last + (1.0 - gam2) * B_last)
    f2 = qh(last['h2'], a2) - ((1.0 - gam1) * A_last + gam2 * B_last)

    if len(d2s) >= 20:
        m = len(d2s)
        if m > 40:
            m = 40
        d1_use = sum(d1s[-m:]) / m
        d2_use = sum(d2s[-m:]) / m
    else:
        d1_use = f1
        d2_use = f2
    scenarios = [(d1_use, d2_use)]

    osc = False
    if len(d2s) >= 40:
        mean1 = sum(d1s) / len(d1s)
        mean2 = sum(d2s) / len(d2s)
        cr1 = 0
        prev = 0
        for v in d1s:
            sg = 1 if v > mean1 else -1
            if prev != 0 and sg != prev:
                cr1 += 1
            prev = sg
        cr2 = 0
        prev = 0
        for v in d2s:
            sg = 1 if v > mean2 else -1
            if prev != 0 and sg != prev:
                cr2 += 1
            prev = sg
        rng1 = max(d1s) - min(d1s)
        rng2 = max(d2s) - min(d2s)
        if (rng2 > 0.001 and cr2 >= 2) or (rng1 > 0.001 and cr1 >= 2):
            osc = True
            r1 = max(abs(min(d1s) - mean1), abs(max(d1s) - mean1))
            r2 = max(abs(min(d2s) - mean2), abs(max(d2s) - mean2))
            scenarios = [(mean1 - r1, mean2 - r2), (mean1 + r1, mean2 + r2)]

    ulim_t = ulim - 0.05
    v_t = 11.4

    hb_lo = h2_lo + 0.008
    hb_hi = h2_hi - 0.008
    if hb_lo > hb_hi:
        hb_lo = h2_lo
        hb_hi = h2_hi
    h2m_lo = max(0.02, hb_lo)
    h2m_hi = min(1.5, hb_hi)
    h1m_lo = max(0.02, lo_lim)
    h1m_hi = min(1.5, hi_lim)

    q1_lo = qh(h1m_lo, a1)
    q1_hi = qh(h1m_hi, a1)
    q2_lo = qh(h2m_lo, a2)
    q2_hi = qh(h2m_hi, a2)
    lo_b = max(q1_lo, Qt - q2_hi)
    hi_b = min(q1_hi, Qt - q2_lo)
    if lo_b > hi_b:
        mid = 0.5 * (lo_b + hi_b)
        lo_b = mid
        hi_b = mid
    cand = []
    K = 60
    if hi_b - lo_b < 1.0e-12:
        cand.append(lo_b)
    else:
        for k in range(K + 1):
            cand.append(lo_b + (hi_b - lo_b) * k / K)
    q1_now = qh(h1_cur, a1)
    if q1_now < lo_b:
        q1_now = lo_b
    if q1_now > hi_b:
        q1_now = hi_b
    cand.append(q1_now)

    best_q1 = q1_now
    best_c = None
    for q1 in cand:
        q2 = Qt - q1
        if q1 <= 1.0e-7 or q2 <= 1.0e-7:
            continue
        c = 0.0
        bad = False
        for si in range(len(scenarios)):
            dd1 = scenarios[si][0]
            dd2 = scenarios[si][1]
            Q1 = q1 - dd1
            Q2 = q2 - dd2
            B = (4.0 * Q1 - Q2) / 3.0
            A = (4.0 * Q2 - Q1) / 3.0
            if A <= 1.0e-7 or B <= 1.0e-7:
                bad = True
                break
            h3p = (0.8 * B / a3) ** 2 / (2.0 * g)
            h4p = (0.8 * A / a4) ** 2 / (2.0 * g)
            if h3p > ulim_t:
                c += 6000.0 * (h3p - ulim_t)
            if h4p > ulim_t:
                c += 6000.0 * (h4p - ulim_t)
            v1p = A / k1e
            v2p = B / k2e
            if v1p > v_t:
                c += 900.0 * (v1p - v_t)
            if v2p > v_t:
                c += 900.0 * (v2p - v_t)
        if bad:
            continue
        h1p = hq(q1, a1)
        h2p = hq(q2, a2)
        if h2p - err2 < h2_lo:
            c += 2500.0 * (h2_lo - (h2p - err2))
        if h2p + err2 > h2_hi:
            c += 2500.0 * ((h2p + err2) - h2_hi)
        c += 250.0 * (abs(h1p - h1_cur) + abs(h2p - h2_cur))
        if best_c is None or c < best_c:
            best_c = c
            best_q1 = q1

    h1_des = hq(best_q1, a1)
    h2_des = hq(Qt - best_q1, a2)
    if h1_des < lo_lim:
        h1_des = lo_lim
    if h1_des > hi_lim:
        h1_des = hi_lim
    if h2_des < lo_lim:
        h2_des = lo_lim
    if h2_des > hi_lim:
        h2_des = hi_lim
    if h2_des < h2_lo:
        h2_des = h2_lo
    if h2_des > h2_hi:
        h2_des = h2_hi

    step = 0.04
    if h1_des - h1_cur > step:
        h1_des = h1_cur + step
    elif h1_cur - h1_des > step:
        h1_des = h1_cur - step
    if h2_des - h2_cur > step:
        h2_des = h2_cur + step
    elif h2_cur - h2_des > step:
        h2_des = h2_cur - step

    if abs(h1_des - h1_cur) < 0.004 and abs(h2_des - h2_cur) < 0.004:
        h1_des = h1_cur
        h2_des = h2_cur

    mode = 'recent-load'
    if osc:
        mode = 'oscillation-damped'
    elif len(d2s) < 20:
        mode = 'fallback'
    diag = 'model split (%s) d1=%.0f d2=%.0f mL/s h2err=%.3f -> h1=%.3f h2=%.3f' % (mode, 1000.0 * d1_use, 1000.0 * d2_use, err2, h1_des, h2_des)

    return {'diagnosis': diag, 'adjusted_setpoints': {'h1': h1_des, 'h2': h2_des}}
