def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    c1 = 0.20 * 0.00085
    c2 = 0.20 * 0.00095
    g = 9.81
    s2g = math.sqrt(2.0 * g)

    try:
        ah1 = float(active_setpoints['h1'])
        ah2 = float(active_setpoints['h2'])
    except Exception:
        ah1 = 0.30
        ah2 = 0.35
    try:
        Qtarget = float(objectives['production_target'])
        lims = objectives['setpoint_limits']
        lo_lim = float(lims[0])
        hi_lim = float(lims[1])
        band = objectives['h2_band']
        h2lo = float(band[0])
        h2hi = float(band[1])
        ulim = float(objectives['upper_level_limit'])
    except Exception:
        Qtarget = 16.35
        lo_lim = 0.02
        hi_lim = 1.5
        h2lo = 0.25
        h2hi = 0.45
        ulim = 0.75

    n = len(telemetry_window)
    if n == 0:
        return {'diagnosis': 'no telemetry; holding setpoints',
                'adjusted_setpoints': {'h1': ah1, 'h2': ah2}}

    m = 20
    if n < m:
        m = n
    w = telemetry_window[n - m:]

    ts = [x['time'] for x in w]
    tm = sum(ts) / m
    var = 0.0
    for t in ts:
        var += (t - tm) * (t - tm)
    if var < 1e-9:
        var = 1e-9

    sh1 = 0.0
    sh2 = 0.0
    sh3 = 0.0
    sh4 = 0.0
    sv1 = 0.0
    sv2 = 0.0
    for x in w:
        sh1 += x['h1']
        sh2 += x['h2']
        sh3 += x['h3']
        sh4 += x['h4']
        sv1 += x['v1']
        sv2 += x['v2']
    h1 = sh1 / m
    h2 = sh2 / m
    h3 = sh3 / m
    h4 = sh4 / m
    v1 = sv1 / m
    v2 = sv2 / m

    n1 = 0.0
    n2 = 0.0
    n3 = 0.0
    n4 = 0.0
    for i in range(m):
        dt = ts[i] - tm
        n1 += dt * (w[i]['h1'] - h1)
        n2 += dt * (w[i]['h2'] - h2)
        n3 += dt * (w[i]['h3'] - h3)
        n4 += dt * (w[i]['h4'] - h4)
    dh1 = n1 / var
    dh2 = n2 / var
    dh3 = n3 / var
    dh4 = n4 / var

    if h1 < 0.001:
        h1 = 0.001
    if h2 < 0.001:
        h2 = 0.001
    if h3 < 0.0:
        h3 = 0.0
    if h4 < 0.0:
        h4 = 0.0
    if v1 < 0.5:
        v1 = 0.5
    if v2 < 0.5:
        v2 = 0.5

    q3 = a3 * s2g * math.sqrt(h3)
    q4 = a4 * s2g * math.sqrt(h4)
    beta2 = (q3 + dh3) / v2
    beta1 = (q4 + dh4) / v1
    if beta1 < 0.00030:
        beta1 = 0.00030
    if beta1 > 0.00130:
        beta1 = 0.00130
    if beta2 < 0.00035:
        beta2 = 0.00035
    if beta2 > 0.00140:
        beta2 = 0.00140

    d1 = a1 * s2g * math.sqrt(h1) + dh1 - q3 - c1 * v1
    d2 = a2 * s2g * math.sqrt(h2) + dh2 - q4 - c2 * v2
    if d1 > 0.006:
        d1 = 0.006
    if d1 < -0.006:
        d1 = -0.006
    if d2 > 0.006:
        d2 = 0.006
    if d2 < -0.006:
        d2 = -0.006

    Qm = Qtarget / 1000.0
    det = c1 * c2 - beta1 * beta2
    if det > -1e-9:
        det = -1e-7

    ultgt = ulim - 0.05
    h2hi_t = h2hi - 0.01
    h2lo_t = h2lo + 0.01

    def cost_of(h1c, h2c):
        r1 = a1 * s2g * math.sqrt(h1c) - d1
        r2 = a2 * s2g * math.sqrt(h2c) - d2
        v1p = (c2 * r1 - beta2 * r2) / det
        v2p = (c1 * r2 - beta1 * r1) / det
        if v2p > 0.0:
            h3p = (beta2 * v2p / a3) ** 2 / (2.0 * g)
        else:
            h3p = 0.0
        if v1p > 0.0:
            h4p = (beta1 * v1p / a4) ** 2 / (2.0 * g)
        else:
            h4p = 0.0
        Qp = (a1 * s2g * math.sqrt(h1c) + a2 * s2g * math.sqrt(h2c)) * 1000.0
        ct = 100.0 * (abs(h1c - ah1) + abs(h2c - ah2))
        ct += 3000.0 * abs(Qp - Qtarget)
        if h3p > ultgt:
            ct += 800.0 * (h3p - ultgt)
        if h4p > ultgt:
            ct += 800.0 * (h4p - ultgt)
        if h2c > h2hi_t:
            ct += 900.0 * (h2c - h2hi_t)
        if h2c < h2lo_t:
            ct += 900.0 * (h2lo_t - h2c)
        if v1p > 12.0:
            ct += 3000.0 * (v1p - 12.0)
        if v2p > 12.0:
            ct += 3000.0 * (v2p - 12.0)
        if v1p < 1.0:
            ct += 3000.0 * (1.0 - v1p)
        if v2p < 1.0:
            ct += 3000.0 * (1.0 - v2p)
        return ct

    best = cost_of(ah1, ah2)
    bh1 = ah1
    bh2 = ah2
    is_active = True

    h1maxp = (Qm / (a1 * s2g)) ** 2
    h1_lo = lo_lim
    if h1_lo < 0.03:
        h1_lo = 0.03
    h1_hi = hi_lim
    if h1_hi > 1.45:
        h1_hi = 1.45
    if h1_hi > h1maxp * 0.998:
        h1_hi = h1maxp * 0.998

    if h1_hi > h1_lo + 1e-4:
        N = 60
        step0 = (h1_hi - h1_lo) / N
        for i in range(N + 1):
            h1c = h1_lo + step0 * i
            rem = Qm - a1 * s2g * math.sqrt(h1c)
            if rem <= 1e-9:
                continue
            h2c = (rem / (a2 * s2g)) ** 2
            if h2c < 0.02 or h2c > 1.5:
                continue
            ct = cost_of(h1c, h2c)
            if ct < best:
                best = ct
                bh1 = h1c
                bh2 = h2c
                is_active = False
        if not is_active:
            st = step0
            for _ in range(4):
                st = st / 6.0
                lo = bh1 - st
                hi = bh1 + st
                if lo < h1_lo:
                    lo = h1_lo
                if hi > h1_hi:
                    hi = h1_hi
                for i in range(13):
                    h1c = lo + (hi - lo) * i / 12.0
                    rem = Qm - a1 * s2g * math.sqrt(h1c)
                    if rem <= 1e-9:
                        continue
                    h2c = (rem / (a2 * s2g)) ** 2
                    if h2c < 0.02 or h2c > 1.5:
                        continue
                    ct = cost_of(h1c, h2c)
                    if ct < best:
                        best = ct
                        bh1 = h1c
                        bh2 = h2c

    if is_active:
        return {'diagnosis': 'holding setpoints: Q on target and h3/h4 within margin',
                'adjusted_setpoints': {'h1': round(ah1, 4), 'h2': round(ah2, 4)}}

    step = bh1 - ah1
    if step > 0.10:
        bh1 = ah1 + 0.10
    if step < -0.10:
        bh1 = ah1 - 0.10
    if bh1 < h1_lo:
        bh1 = h1_lo
    if bh1 > h1_hi:
        bh1 = h1_hi
    rem = Qm - a1 * s2g * math.sqrt(bh1)
    if rem <= 1e-9:
        return {'diagnosis': 'target not achievable; holding',
                'adjusted_setpoints': {'h1': round(ah1, 4), 'h2': round(ah2, 4)}}
    bh2 = (rem / (a2 * s2g)) ** 2
    if bh2 < 0.02:
        bh2 = 0.02
    if bh2 > 1.5:
        bh2 = 1.5
    bh1 = round(bh1, 4)
    bh2 = round(bh2, 4)

    if bh1 < ah1:
        diag = 'shift production to tank2 (lower h1, higher h2) to relieve tank3/v2'
    else:
        diag = 'shift production to tank1 (higher h1, lower h2) to relieve tank4/v1'
    return {'diagnosis': diag, 'adjusted_setpoints': {'h1': bh1, 'h2': bh2}}
