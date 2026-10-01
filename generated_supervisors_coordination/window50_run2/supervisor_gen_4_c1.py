def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    g1 = 0.20
    g2 = 0.20
    K1n = 0.85
    K2n = 0.95
    g = 9.81
    Q_t = float(objectives["production_target"])
    h2lo, h2hi = objectives["h2_band"]
    ulim = float(objectives["upper_level_limit"])
    slo, shi = objectives["setpoint_limits"]
    ah1 = float(active_setpoints["h1"])
    ah2 = float(active_setpoints["h2"])

    n = len(telemetry_window)
    if n == 0:
        return {"diagnosis": "no data", "adjusted_setpoints": {"h1": ah1, "h2": ah2}}

    Ws = telemetry_window[-30:] if n >= 30 else telemetry_window
    ms = len(Ws)
    def avg(key, arr):
        return sum(s[key] for s in arr) / len(arr)
    h1c = avg("h1", Ws); h2c = avg("h2", Ws)
    h3c = avg("h3", Ws); h4c = avg("h4", Ws)
    v1c = avg("v1", Ws); v2c = avg("v2", Ws)

    def slope(key, arr):
        m = len(arr)
        if m < 3:
            return 0.0
        tb = (m - 1) / 2.0
        num = 0.0; den = 0.0
        for i, s in enumerate(arr):
            dt = i - tb
            num += dt * s[key]
            den += dt * dt
        if den <= 0.0:
            return 0.0
        return num / den

    s1 = slope("h1", Ws)
    s2 = slope("h2", Ws)
    s3 = slope("h3", Ws)
    s4 = slope("h4", Ws)

    Wq = telemetry_window[-12:] if n >= 12 else telemetry_window
    Qc = avg("production", Wq)
    sQ = slope("production", Wq)

    def qf(h, a):
        if h <= 0.0:
            return 0.0
        return 1000.0 * a * math.sqrt(2.0 * g * h)
    def hf(qq, a):
        if qq <= 0.0:
            return 0.0
        return (qq / (1000.0 * a)) ** 2 / (2.0 * g)

    q1c = qf(h1c, a1); q2c = qf(h2c, a2)
    q3c = qf(h3c, a3); q4c = qf(h4c, a4)

    def eff_gain(qup, v, gam, Kn):
        if v > 1.0:
            e = qup / ((1.0 - gam) * v)
            lo = 0.35 * Kn; hi = 1.25 * Kn
            if e < lo: e = lo
            if e > hi: e = hi
            return e
        return Kn
    k1e = eff_gain(q4c, v1c, g1, K1n)
    k2e = eff_gain(q3c, v2c, g2, K2n)

    d1e = q1c - q3c - g1 * k1e * v1c + 400.0 * s1
    d2e = q2c - q4c - g2 * k2e * v2c + 400.0 * s2
    if d1e > 3.0: d1e = 3.0
    if d1e < -3.0: d1e = -3.0
    if d2e > 3.0: d2e = 3.0
    if d2e < -3.0: d2e = -3.0

    Qpred = Qc + sQ * 6.0
    bias = 0.25 * (Q_t - Qpred)
    if bias > 0.6: bias = 0.6
    if bias < -0.6: bias = -0.6
    if abs(Qc - Q_t) < 0.08:
        bias = 0.0
    Qeff = Q_t + bias
    if Qeff < 1.0: Qeff = 1.0

    al = g1 / (1.0 - g1)
    be = g2 / (1.0 - g2)
    det = 1.0 - al * be
    H_pred = 25.0
    margin_ss = 0.06

    def evaluate(h1_sp):
        if h1_sp < 0.02 or h1_sp > 1.5:
            return None
        if h1_sp < slo or h1_sp > shi:
            return None
        q1 = qf(h1_sp, a1)
        q2 = Qeff - q1
        if q2 <= 0.05:
            return None
        h2_sp = hf(q2, a2)
        if h2_sp < 0.02 or h2_sp > 1.5:
            return None
        rhs1 = q1 - d1e
        rhs2 = q2 - d2e
        q4 = (rhs2 - be * rhs1) / det
        q3 = rhs1 - al * q4
        neg_pen = 0.0
        if q3 < 0.0:
            neg_pen += 400.0 * (-q3)
            q3 = 0.0
        if q4 < 0.0:
            neg_pen += 400.0 * (-q4)
            q4 = 0.0
        h3_ss = hf(q3, a3)
        h4_ss = hf(q4, a4)
        v1_ss = q4 / ((1.0 - g1) * k1e) if k1e > 0.0 else 0.0
        v2_ss = q3 / ((1.0 - g2) * k2e) if k2e > 0.0 else 0.0
        if v1_ss < 0.0: v1_ss = 0.0
        if v2_ss < 0.0: v2_ss = 0.0
        h3_ext = h3c + s3 * H_pred
        h4_ext = h4c + s4 * H_pred
        h3_pred = h3_ss if h3_ss > h3_ext else h3_ext
        h4_pred = h4_ss if h4_ss > h4_ext else h4_ext
        thr = ulim - margin_ss
        viol = 0.0
        if h3_pred > thr:
            viol += 1500.0 * (h3_pred - thr)
        if h4_pred > thr:
            viol += 1500.0 * (h4_pred - thr)
        cur3 = h3c - thr
        if cur3 < 0.0: cur3 = 0.0
        cur4 = h4c - thr
        if cur4 < 0.0: cur4 = 0.0
        viol += 200.0 * cur3 * v2_ss + 200.0 * cur4 * v1_ss
        band = 0.0
        if h2_sp < h2lo:
            band += 400.0 * (h2lo - h2_sp)
        if h2_sp > h2hi:
            band += 400.0 * (h2_sp - h2hi)
        pump = 0.0
        if v1_ss > 12.0: pump += 80.0 * (v1_ss - 12.0)
        if v1_ss < 1.0: pump += 80.0 * (1.0 - v1_ss)
        if v2_ss > 12.0: pump += 80.0 * (v2_ss - 12.0)
        if v2_ss < 1.0: pump += 80.0 * (1.0 - v2_ss)
        travel = abs(h1_sp - ah1) + abs(h2_sp - ah2)
        cost = 200.0 * travel + viol + band + pump + neg_pen
        return (cost, h1_sp, h2_sp, h3_ss, h4_ss, v1_ss, v2_ss)

    best = None
    h_lo = 0.05
    if slo > h_lo: h_lo = slo
    h_hi = 0.9
    if shi < h_hi: h_hi = shi
    if h_hi < h_lo:
        h_lo = h_hi
    h = h_lo
    while h <= h_hi + 1e-9:
        r = evaluate(h)
        if r is not None:
            if best is None or r[0] < best[0]:
                best = r
        h += 0.005
    if best is not None:
        c = best[1]
        i = -20
        while i <= 20:
            r = evaluate(c + i * 0.0005)
            if r is not None:
                if r[0] < best[0]:
                    best = r
            i += 1
    if best is None:
        h1f = min(max(ah1, slo), shi)
        h2f = min(max(ah2, slo), shi)
        return {"diagnosis": "fallback: no feasible candidate", "adjusted_setpoints": {"h1": h1f, "h2": h2f}}
    cost, h1s, h2s, h3ss, h4ss, v1s, v2s = best
    if h1s < slo: h1s = slo
    if h1s > shi: h1s = shi
    if h2s < slo: h2s = slo
    if h2s > shi: h2s = shi
    diag = "model+bias: d1=%.2f d2=%.2f Qeff=%.2f pred h3=%.2f h4=%.2f v1=%.1f v2=%.1f" % (d1e, d2e, Qeff, h3ss, h4ss, v1s, v2s)
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1s, "h2": h2s}}