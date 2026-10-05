def supervise(telemetry_window, active_setpoints, objectives):
    TG = 19.62
    A1 = 0.0035
    A2 = 0.003
    A3 = 0.002
    A4 = 0.0025
    K1 = 0.00085
    K2 = 0.00095
    GM1 = 0.20
    GM2 = 0.20

    def sq(h):
        if h <= 0.0:
            return 0.0
        return math.sqrt(TG * h)

    def lvl(x, a):
        if a <= 0.0:
            return 0.0
        t = x / a
        return t * t / TG

    sp1 = float(active_setpoints['h1'])
    sp2 = float(active_setpoints['h2'])
    lo_lim = float(objectives['setpoint_limits'][0])
    hi_lim = float(objectives['setpoint_limits'][1])
    b_lo = float(objectives['h2_band'][0])
    b_hi = float(objectives['h2_band'][1])
    uplim = float(objectives['upper_level_limit'])
    tgt = float(objectives['production_target'])

    W = telemetry_window
    n = len(W)
    if n < 5:
        return {'diagnosis': 'warming up', 'adjusted_setpoints': {'h1': sp1, 'h2': sp2}}

    last = W[n - 1]
    h1 = float(last['h1'])
    h2 = float(last['h2'])
    h3 = float(last['h3'])
    h4 = float(last['h4'])
    v1 = float(last['v1'])
    v2 = float(last['v2'])

    m = 15
    if m > n - 1:
        m = n - 1
    prev = W[n - 1 - m]
    dt = float(last['time']) - float(prev['time'])
    if dt <= 0.0:
        dt = 1.0
    dh1 = (h1 - float(prev['h1'])) / dt
    dh2 = (h2 - float(prev['h2'])) / dt

    d1 = dh1 + A1 * sq(h1) - A3 * sq(h3) - GM1 * K1 * v1
    d2 = dh2 + A2 * sq(h2) - A4 * sq(h4) - GM2 * K2 * v2
    if d1 > 0.006:
        d1 = 0.006
    elif d1 < -0.006:
        d1 = -0.006
    if d2 > 0.006:
        d2 = 0.006
    elif d2 < -0.006:
        d2 = -0.006

    Xtot = tgt / 1000.0
    if Xtot <= 1.0e-9:
        return {'diagnosis': 'no target', 'adjusted_setpoints': {'h1': sp1, 'h2': sp2}}

    x1c = A1 * sq(sp1)
    x2c = A2 * sq(sp2)
    den = 1.0 - GM1 - GM2

    def flows(x1):
        x2 = Xtot - x1
        p2 = ((1.0 - GM1) * (x1 - d1) - GM1 * (x2 - d2)) / den
        p1 = (GM2 * (x1 - d1) - (1.0 - GM2) * (x2 - d2)) / (GM1 + GM2 - 1.0)
        return p1, p2

    def penalty(h1c, h2c, h3c, h4c, v1c, v2c):
        pen = 0.0
        if h2c < b_lo:
            pen += 15.0 * (b_lo - h2c)
        elif h2c > b_hi:
            pen += 15.0 * (h2c - b_hi)
        if h3c > uplim:
            pen += 15.0 * (h3c - uplim)
        if h4c > uplim:
            pen += 15.0 * (h4c - uplim)
        if v1c > 11.2:
            pen += 20.0 * (v1c - 11.2)
        if v2c > 11.2:
            pen += 20.0 * (v2c - 11.2)
        if v1c < 1.0:
            pen += 20.0 * (1.0 - v1c)
        if v2c < 1.0:
            pen += 20.0 * (1.0 - v2c)
        if h1c < 0.05:
            pen += 600.0 * (0.05 - h1c)
        if h1c > 1.45:
            pen += 600.0 * (h1c - 1.45)
        if h2c < 0.05:
            pen += 600.0 * (0.05 - h2c)
        if h2c > 1.45:
            pen += 600.0 * (h2c - 1.45)
        return pen

    p1cur, p2cur = flows(x1c)
    if p1cur < 1.0e-5:
        p1cur = 1.0e-5
    if p2cur < 1.0e-5:
        p2cur = 1.0e-5
    if v1 > 11.3:
        k1u = p1cur / v1
    else:
        k1u = K1
    if v2 > 11.3:
        k2u = p2cur / v2
    else:
        k2u = K2
    if k1u < 0.3 * K1:
        k1u = 0.3 * K1
    if k1u > 2.0 * K1:
        k1u = 2.0 * K1
    if k2u < 0.3 * K2:
        k2u = 0.3 * K2
    if k2u > 2.0 * K2:
        k2u = 2.0 * K2

    h1_lo = lo_lim
    if h1_lo < 0.05:
        h1_lo = 0.05
    h1_hi = hi_lim
    if h1_hi > 1.45:
        h1_hi = 1.45
    h2_lo = lo_lim
    if h2_lo < 0.05:
        h2_lo = 0.05
    h2_hi = hi_lim
    if h2_hi > 1.45:
        h2_hi = 1.45
    xlo = A1 * sq(h1_lo)
    t = Xtot - A2 * sq(h2_hi)
    if t > xlo:
        xlo = t
    xhi = A1 * sq(h1_hi)
    t = Xtot - A2 * sq(h2_lo)
    if t < xhi:
        xhi = t
    if xhi < xlo:
        xm = 0.5 * (xlo + xhi)
        xlo = xm
        xhi = xm

    NP = 300
    best_h1 = sp1
    best_h2 = sp2
    best_pen = 1.0e18
    i = 0
    while i <= NP:
        x1 = xlo + (xhi - xlo) * i / NP
        x2 = Xtot - x1
        if x1 > 1.0e-6 and x2 > 1.0e-6:
            p1c, p2c = flows(x1)
            if p1c > 1.0e-6 and p2c > 1.0e-6:
                h1c = lvl(x1, A1)
                h2c = lvl(x2, A2)
                h3c = lvl((1.0 - GM2) * p2c, A3)
                h4c = lvl((1.0 - GM1) * p1c, A4)
                v1c = p1c / k1u
                v2c = p2c / k2u
                pen = abs(h1c - sp1) + abs(h2c - sp2) + penalty(h1c, h2c, h3c, h4c, v1c, v2c)
                if pen < best_pen:
                    best_pen = pen
                    best_h1 = h1c
                    best_h2 = h2c
        i += 1

    pen_cur = 1.0e6
    if x1c > 1.0e-6 and x2c > 1.0e-6:
        p1a, p2a = flows(x1c)
        if p1a > 1.0e-6 and p2a > 1.0e-6:
            h3a = lvl((1.0 - GM2) * p2a, A3)
            h4a = lvl((1.0 - GM1) * p1a, A4)
            pen_cur = penalty(sp1, sp2, h3a, h4a, p1a / k1u, p2a / k2u)

    off_manifold = abs(x1c + x2c - Xtot) > 1.0e-5
    if (not off_manifold) and pen_cur <= best_pen + 0.004:
        best_h1 = sp1
        best_h2 = sp2

    if best_h1 < lo_lim:
        best_h1 = lo_lim
    if best_h1 > hi_lim:
        best_h1 = hi_lim
    if best_h2 < lo_lim:
        best_h2 = lo_lim
    if best_h2 > hi_lim:
        best_h2 = hi_lim

    diag = 'target %.2f; d1 %.2f d2 %.2f L/s; sp %.3f/%.3f' % (tgt, d1 * 1000.0, d2 * 1000.0, best_h1, best_h2)
    return {'diagnosis': diag, 'adjusted_setpoints': {'h1': best_h1, 'h2': best_h2}}