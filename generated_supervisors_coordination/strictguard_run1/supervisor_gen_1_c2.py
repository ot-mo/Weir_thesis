def supervise(telemetry_window, active_setpoints, objectives):
    A1 = 0.0035
    A2 = 0.003
    A3 = 0.002
    A4 = 0.0025
    SF = math.sqrt(2.0 * 9.81)

    Qt = float(objectives["production_target"])
    sp_lo = float(objectives["setpoint_limits"][0])
    sp_hi = float(objectives["setpoint_limits"][1])
    h2_lo = float(objectives["h2_band"][0])
    h2_hi = float(objectives["h2_band"][1])
    uplim = float(objectives["upper_level_limit"])

    def hq(q, a):
        if q < 0.0:
            q = 0.0
        return (q / 1000.0 / (a * SF)) ** 2

    def qh(h, a):
        if h < 0.0:
            h = 0.0
        return a * SF * math.sqrt(h) * 1000.0

    tw = telemetry_window
    last = tw[-1]
    h3m = float(last["h3"])
    h4m = float(last["h4"])
    v1m = float(last["v1"])
    v2m = float(last["v2"])

    n = len(tw)
    kk = 20
    if kk > n - 1:
        kk = n - 1
    if kk < 1:
        kk = 1
    dt = tw[-1]["time"] - tw[-1 - kk]["time"]
    if dt <= 0.0:
        dt = 1.0
    sh3 = (tw[-1]["h3"] - tw[-1 - kk]["h3"]) / dt
    sh4 = (tw[-1]["h4"] - tw[-1 - kk]["h4"]) / dt
    HL = 50.0
    h3p = h3m + sh3 * HL
    h4p = h4m + sh4 * HL

    H3_S = 0.68
    H3_H = uplim
    H4_S = 0.60
    H4_H = uplim
    V2_S = 10.0
    V2_H = 12.0
    V1_S = 10.8
    V1_H = 12.0

    def st(x, s, h):
        if x <= s or h <= s:
            return 0.0
        return (x - s) / (h - s)

    s3 = st(h3p, H3_S, H3_H)
    t = st(v2m, V2_S, V2_H)
    if t > s3:
        s3 = t
    s4 = st(h4p, H4_S, H4_H)
    t = st(v1m, V1_S, V1_H)
    if t > s4:
        s4 = t
    if s3 > 3.0:
        s3 = 3.0
    if s4 > 3.0:
        s4 = 3.0

    q1n = qh(0.30, A1)
    q2n = qh(0.35, A2)
    QN = q1n + q2n
    sc = Qt / QN
    h1b = hq(q1n * sc, A1)
    h2b = hq(q2n * sc, A2)

    sp1 = float(active_setpoints["h1"])
    sp2 = float(active_setpoints["h2"])
    qsum = qh(sp1, A1) + qh(sp2, A2)

    lo1 = sp_lo
    if lo1 < 0.05:
        lo1 = 0.05
    hi1 = sp_hi
    if hi1 > 1.4:
        hi1 = 1.4
    lo2 = sp_lo
    if lo2 < h2_lo + 0.002:
        lo2 = h2_lo + 0.002
    hi2 = sp_hi
    if hi2 > h2_hi - 0.002:
        hi2 = h2_hi - 0.002
    if hi2 < lo2:
        hi2 = lo2

    if abs(qsum - Qt) > 0.02:
        h2c = h2b
        h1c = hq(Qt - qh(h2c, A2), A1)
    else:
        d = 0.03 * (s3 - s4)
        if d > 0.04:
            d = 0.04
        if d < -0.04:
            d = -0.04
        if -0.0015 < d < 0.0015:
            d = 0.0
        h2c = sp2 + d
        if h2c < lo2:
            h2c = lo2
        if h2c > hi2:
            h2c = hi2
        h1c = hq(Qt - qh(h2c, A2), A1)

    if h1c < lo1 or h1c > hi1:
        if h1c < lo1:
            h1c = lo1
        else:
            h1c = hi1
        h2c = hq(Qt - qh(h1c, A1), A2)
    if h1c < lo1:
        h1c = lo1
    if h1c > hi1:
        h1c = hi1
    if h2c < lo2:
        h2c = lo2
    if h2c > hi2:
        h2c = hi2

    diag = ("Q*%.2f; h3=%.3f v2=%.2f h4=%.3f v1=%.2f; shift=%.3f"
            % (Qt, h3m, v2m, h4m, v1m, s3 - s4))
    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"h1": h1c, "h2": h2c},
    }
