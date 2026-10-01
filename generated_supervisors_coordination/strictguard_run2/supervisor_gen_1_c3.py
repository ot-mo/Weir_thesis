def supervise(telemetry_window, active_setpoints, objectives):
    A1 = 0.0035
    A2 = 0.003
    A3 = 0.002
    A4 = 0.0025
    T2G = 2.0 * 9.81
    K1N = 0.00085
    K2N = 0.00095

    def flw(a, h):
        if h <= 0.0:
            return 0.0
        return a * math.sqrt(T2G * h)

    def lvl(a, f):
        if f <= 0.0:
            return 0.0
        t = f / a
        return t * t / T2G

    def capv(x, c):
        if x < c:
            return x
        return c

    w = telemetry_window
    n = len(w)
    h1a = active_setpoints["h1"]
    h2a = active_setpoints["h2"]
    if n < 3:
        return {"diagnosis": "insufficient telemetry; holding setpoints",
                "adjusted_setpoints": {"h1": h1a, "h2": h2a}}

    last = w[-1]
    h1m = last["h1"]
    h2m = last["h2"]
    h3m = last["h3"]
    h4m = last["h4"]
    v1m = last["v1"]
    v2m = last["v2"]

    NF = 15
    if NF > n:
        NF = n
    seg = w[n - NF:]
    xb = 0.0
    for s in seg:
        xb += s["time"]
    xb = xb / NF
    sxx = 0.0
    for s in seg:
        dx = s["time"] - xb
        sxx += dx * dx
    if sxx < 1e-6:
        sxx = 1.0

    def slope_of(key):
        yb = 0.0
        for s in seg:
            yb += s[key]
        yb = yb / NF
        num = 0.0
        for s in seg:
            num += (s["time"] - xb) * (s[key] - yb)
        return num / sxx

    s3 = slope_of("h3")
    s4 = slope_of("h4")

    f1m = flw(A1, h1m)
    f2m = flw(A2, h2m)
    f3m = flw(A3, h3m)
    f4m = flw(A4, h4m)

    P2i = (s3 + f3m) / 0.8
    P1i = (s4 + f4m) / 0.8
    if P2i < 1e-6:
        P2i = 1e-6
    if P1i < 1e-6:
        P1i = 1e-6

    P2n = (0.8 * f1m - 0.2 * f2m) / 0.6
    P1n = (0.8 * f2m - 0.2 * f1m) / 0.6

    dP2 = P2i - P2n
    dP1 = P1i - P1n
    if dP2 > 0.008:
        dP2 = 0.008
    elif dP2 < -0.008:
        dP2 = -0.008
    if dP1 > 0.008:
        dP1 = 0.008
    elif dP1 < -0.008:
        dP1 = -0.008

    k1e = K1N
    k2e = K2N
    if v1m > 2.0:
        t = P1i / v1m
        if 0.35 * K1N < t < 1.7 * K1N:
            k1e = t
    if v2m > 2.0:
        t = P2i / v2m
        if 0.35 * K2N < t < 1.7 * K2N:
            k2e = t

    Q = objectives["production_target"] / 1000.0
    if Q < 1e-5:
        Q = 1e-5
    h2lo = objectives["h2_band"][0]
    h2hi = objectives["h2_band"][1]
    UL = objectives["upper_level_limit"]
    sp_lo = objectives["setpoint_limits"][0]
    sp_hi = objectives["setpoint_limits"][1]

    UT = UL - 0.07
    if UT > 0.68:
        UT = 0.68
    if UT < 0.25:
        UT = 0.25

    def predict(f1p):
        f2p = Q - f1p
        if f1p <= 0.0 or f2p <= 0.0:
            return None
        P2p = (0.8 * f1p - 0.2 * f2p) / 0.6 + dP2
        P1p = (0.8 * f2p - 0.2 * f1p) / 0.6 + dP1
        if P1p <= 0.0 or P2p <= 0.0:
            return None
        return (lvl(A1, f1p), lvl(A2, f2p), lvl(A3, 0.8 * P2p),
                lvl(A4, 0.8 * P1p), P1p / k1e, P2p / k2e)

    def cost(pr):
        if pr is None:
            return 1e12
        h1p = pr[0]
        h2p = pr[1]
        h3p = pr[2]
        h4p = pr[3]
        v1p = pr[4]
        v2p = pr[5]
        c = 100.0 * (abs(h1p - h1a) + abs(h2p - h2a))
        up = 0.0
        if h3p > UT:
            up += capv(h3p - UT, 0.06)
        if h4p > UT:
            up += capv(h4p - UT, 0.06)
        c += 4000.0 * up
        bp = 0.0
        if h2p > h2hi:
            bp += capv(h2p - h2hi, 0.06)
        if h2p < h2lo:
            bp += capv(h2lo - h2p, 0.06)
        c += 4000.0 * bp
        sf = 0.0
        if h1p > 1.35:
            sf += capv(h1p - 1.35, 0.45)
        if h1p < 0.025:
            sf += capv(0.025 - h1p, 0.45)
        if h2p > 1.35:
            sf += capv(h2p - 1.35, 0.45)
        if h2p < 0.025:
            sf += capv(0.025 - h2p, 0.45)
        c += 30000.0 * sf
        vv = 0.0
        if v1p > 11.5:
            vv += capv(v1p - 11.5, 2.0)
        if v2p > 11.5:
            vv += capv(v2p - 11.5, 2.0)
        if v1p < 1.6:
            vv += capv(1.6 - v1p, 2.0)
        if v2p < 1.6:
            vv += capv(1.6 - v2p, 2.0)
        c += 1500.0 * vv
        return c

    f1a = flw(A1, h1a)
    ca = cost(predict(f1a))

    hmax = 1.25
    f1_lo = flw(A1, 0.03)
    t = Q - flw(A2, hmax)
    if t > f1_lo:
        f1_lo = t
    f1_hi = flw(A1, hmax)
    t = Q - flw(A2, 0.03)
    if t < f1_hi:
        f1_hi = t
    if f1_hi <= f1_lo:
        f1_lo = Q * 0.05
        if f1_lo < 1e-5:
            f1_lo = 1e-5
        f1_hi = Q - 1e-5
        if f1_hi <= f1_lo:
            f1_hi = f1_lo * 1.01

    lo = f1_lo
    hi = f1_hi
    best_f1 = f1a
    best_c = ca
    for ps in range(5):
        npts = 81
        step = (hi - lo) / (npts - 1)
        for i in range(npts):
            f1p = lo + step * i
            c = cost(predict(f1p))
            if c < best_c - 1e-12:
                best_c = c
                best_f1 = f1p
        span = (hi - lo) * 0.25
        lo = best_f1 - span
        hi = best_f1 + span
        if lo < f1_lo:
            lo = f1_lo
        if hi > f1_hi:
            hi = f1_hi

    if ca - best_c < 3.0:
        best_f1 = f1a

    h1_new = lvl(A1, best_f1)
    f2_new = Q - best_f1
    h2_new = lvl(A2, f2_new)
    if h1_new < sp_lo:
        h1_new = sp_lo
    if h1_new > sp_hi:
        h1_new = sp_hi
    if h2_new < sp_lo:
        h2_new = sp_lo
    if h2_new > sp_hi:
        h2_new = sp_hi

    diag = ("free-split supervisor: dP1=" + str(round(dP1, 5)) + " dP2=" + str(round(dP2, 5))
            + " k1e=" + str(round(k1e, 6)) + " k2e=" + str(round(k2e, 6))
            + " -> h1=" + str(round(h1_new, 3)) + " h2=" + str(round(h2_new, 3)))
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1_new, "h2": h2_new}}
