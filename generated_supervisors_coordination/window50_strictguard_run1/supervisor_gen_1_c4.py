def supervise(telemetry_window, active_setpoints, objectives):
    G = 9.81
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1n = 0.00085
    k2n = 0.00095
    gam1 = 0.20
    gam2 = 0.20
    al1n = (1.0 - gam1) * k1n
    al2n = (1.0 - gam2) * k2n
    r1 = gam1 / (1.0 - gam1)
    r2 = gam2 / (1.0 - gam2)
    QNOM = 16.35286638873749
    sq2g = math.sqrt(2.0 * G)
    try:
        h1_sp = float(active_setpoints["h1"])
        h2_sp = float(active_setpoints["h2"])
        win = telemetry_window
        n = len(win)
        last = win[n - 1]
        h1 = float(last["h1"])
        h2 = float(last["h2"])
        h3 = float(last["h3"])
        h4 = float(last["h4"])
        v1 = float(last["v1"])
        v2 = float(last["v2"])

        def slope(samples, key, m):
            cnt = len(samples)
            i0 = cnt - m
            if i0 < 0:
                i0 = 0
            t0 = samples[i0]["time"]
            k = cnt - i0
            sx = 0.0
            sy = 0.0
            sxx = 0.0
            sxy = 0.0
            for i in range(i0, cnt):
                x = samples[i]["time"] - t0
                y = samples[i][key]
                sx += x
                sy += y
                sxx += x * x
                sxy += x * y
            den = k * sxx - sx * sx
            if den <= 1e-9:
                return 0.0
            return (k * sxy - sx * sy) / den

        m = 9
        if n < 10:
            m = n
        dh1 = slope(win, "h1", m)
        dh2 = slope(win, "h2", m)
        dh3 = slope(win, "h3", m)
        dh4 = slope(win, "h4", m)

        q1o = a1 * math.sqrt(2.0 * G * max(h1, 1e-6))
        q2o = a2 * math.sqrt(2.0 * G * max(h2, 1e-6))
        q3o = a3 * math.sqrt(2.0 * G * max(h3, 1e-6))
        q4o = a4 * math.sqrt(2.0 * G * max(h4, 1e-6))

        vv1 = max(v1, 0.5)
        vv2 = max(v2, 0.5)
        al1 = (q4o + dh4) / vv1
        al2 = (q3o + dh3) / vv2
        loa1 = 0.45 * al1n
        hia1 = 1.55 * al1n
        loa2 = 0.45 * al2n
        hia2 = 1.55 * al2n
        if al1 < loa1:
            al1 = loa1
        if al1 > hia1:
            al1 = hia1
        if al2 < loa2:
            al2 = loa2
        if al2 > hia2:
            al2 = hia2
        be1 = al1 * r1
        be2 = al2 * r2

        d1 = dh1 + q1o - q3o - be1 * v1
        d2 = dh2 + q2o - q4o - be2 * v2
        if d1 < -0.012:
            d1 = -0.012
        if d1 > 0.012:
            d1 = 0.012
        if d2 < -0.012:
            d2 = -0.012
        if d2 > 0.012:
            d2 = 0.012

        Qt = float(objectives["production_target"]) / 1000.0
        slo = float(objectives["setpoint_limits"][0])
        shi = float(objectives["setpoint_limits"][1])
        b_lo = float(objectives["h2_band"][0])
        b_hi = float(objectives["h2_band"][1])
        up_lim = float(objectives["upper_level_limit"])

        det = be1 * be2 - al1 * al2
        if det > -1e-10:
            det = -1e-10

        scale = (Qt * 1000.0 / QNOM) ** 2
        h1r = 0.30 * scale
        h2r = 0.35 * scale

        cap3 = up_lim - 0.07
        cap4 = up_lim - 0.07
        MU = 2.0
        W_CAP = 3000.0
        W_HARD = 100000.0
        W_BAND = 3000.0
        W_SAFE = 1000000.0
        W_PUMP = 300.0

        h2_lo = 0.03
        h2_hi = 0.95
        if slo > h2_lo:
            h2_lo = slo
        if shi < h2_hi:
            h2_hi = shi
        step = 0.002
        N = int((h2_hi - h2_lo) / step) + 1
        best = None
        best_cost = None
        for ii in range(N + 1):
            h2c = h2_lo + ii * step
            if h2c > h2_hi:
                h2c = h2_hi
            q2c = a2 * sq2g * math.sqrt(h2c)
            q1c = Qt - q2c
            if q1c <= 1e-7:
                continue
            h1c = (q1c / (a1 * sq2g)) ** 2
            if h1c < slo or h1c > shi:
                continue
            A = q1c - d1
            B = q2c - d2
            v1p = (be2 * A - al2 * B) / det
            v2p = (be1 * B - al1 * A) / det
            q3p = al2 * v2p
            q4p = al1 * v1p
            if q3p < 0.0:
                q3p = 0.0
            if q4p < 0.0:
                q4p = 0.0
            h3p = (q3p / (a3 * sq2g)) ** 2
            h4p = (q4p / (a4 * sq2g)) ** 2
            cost = abs(h1c - h1_sp) + abs(h2c - h2_sp) + MU * (abs(h1c - h1r) + abs(h2c - h2r))
            if h1c < 0.02:
                cost += W_SAFE * (0.02 - h1c)
            if h1c > 1.5:
                cost += W_SAFE * (h1c - 1.5)
            if h2c < 0.02:
                cost += W_SAFE * (0.02 - h2c)
            if h2c > 1.5:
                cost += W_SAFE * (h2c - 1.5)
            if h2c < b_lo:
                cost += W_BAND * (b_lo - h2c)
            if h2c > b_hi:
                cost += W_BAND * (h2c - b_hi)
            if h3p > cap3:
                cost += W_CAP * (h3p - cap3)
            if h4p > cap4:
                cost += W_CAP * (h4p - cap4)
            if h3p > up_lim:
                cost += W_HARD * (h3p - up_lim)
            if h4p > up_lim:
                cost += W_HARD * (h4p - up_lim)
            if v1p < 1.0:
                cost += W_PUMP * (1.0 - v1p)
            if v1p > 12.0:
                cost += W_PUMP * (v1p - 12.0)
            if v2p < 1.0:
                cost += W_PUMP * (1.0 - v2p)
            if v2p > 12.0:
                cost += W_PUMP * (v2p - 12.0)
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = (h1c, h2c, h3p, h4p, v1p, v2p)

        if best is None:
            h1n = min(shi, max(slo, h1r))
            h2n = min(shi, max(slo, h2r))
            return {
                "diagnosis": "no candidate; using scaled reference",
                "adjusted_setpoints": {"h1": float(h1n), "h2": float(h2n)},
            }

        h1n, h2n, h3p, h4p, v1p, v2p = best
        MAXSTEP = 0.15
        if h1n - h1_sp > MAXSTEP:
            h1n = h1_sp + MAXSTEP
        if h1_sp - h1n > MAXSTEP:
            h1n = h1_sp - MAXSTEP
        if h2n - h2_sp > MAXSTEP:
            h2n = h2_sp + MAXSTEP
        if h2_sp - h2n > MAXSTEP:
            h2n = h2_sp - MAXSTEP
        if h1n < slo:
            h1n = slo
        if h1n > shi:
            h1n = shi
        if h2n < slo:
            h2n = slo
        if h2n > shi:
            h2n = shi
        if abs(h1n - h1_sp) < 5e-4 and abs(h2n - h2_sp) < 5e-4:
            h1n = h1_sp
            h2n = h2_sp
        diag = "pred h3=%.3f h4=%.3f v=(%.2f,%.2f) d1=%.2f d2=%.2f L/s" % (h3p, h4p, v1p, v2p, d1 * 1000.0, d2 * 1000.0)
        return {
            "diagnosis": diag,
            "adjusted_setpoints": {"h1": float(h1n), "h2": float(h2n)},
        }
    except Exception:
        try:
            return {
                "diagnosis": "exception; holding previous setpoints",
                "adjusted_setpoints": {"h1": float(active_setpoints["h1"]), "h2": float(active_setpoints["h2"])},
            }
        except Exception:
            return {
                "diagnosis": "exception",
                "adjusted_setpoints": {"h1": 0.30, "h2": 0.35},
            }
