def supervise(telemetry_window, active_setpoints, objectives):
    G = 9.81
    A1 = 0.0035
    A2 = 0.003
    A3 = 0.002
    A4 = 0.0025
    K1N = 0.00085
    K2N = 0.00095
    ALPHA = 0.25
    SQ2G = math.sqrt(2.0 * G)

    try:
        h1a = float(active_setpoints['h1'])
        h2a = float(active_setpoints['h2'])
    except Exception:
        h1a = 0.30
        h2a = 0.35
    fb = {'h1': h1a, 'h2': h2a}

    try:
        Q_target = float(objectives['production_target']) / 1000.0
        band = objectives['h2_band']
        h2_lo = float(band[0])
        h2_hi = float(band[1])
        ulim = float(objectives['upper_level_limit'])
        slim = objectives['setpoint_limits']
        sp_lo = float(slim[0])
        sp_hi = float(slim[1])
    except Exception:
        return {'diagnosis': 'bad objectives', 'adjusted_setpoints': fb}

    try:
        tw = telemetry_window
        N = len(tw)
        if N < 6 or Q_target <= 0.0:
            return {'diagnosis': 'insufficient data', 'adjusted_setpoints': fb}

        start = N - 30
        if start < 0:
            start = 0
        nw = float(N - start)

        S1 = 0.0
        S2 = 0.0
        S3 = 0.0
        S4 = 0.0
        V1 = 0.0
        V2 = 0.0
        for i in range(start, N):
            s = tw[i]
            x1 = s['h1']
            x2 = s['h2']
            x3 = s['h3']
            x4 = s['h4']
            if x1 < 0.0:
                x1 = 0.0
            if x2 < 0.0:
                x2 = 0.0
            if x3 < 0.0:
                x3 = 0.0
            if x4 < 0.0:
                x4 = 0.0
            S1 += A1 * math.sqrt(2.0 * G * x1)
            S2 += A2 * math.sqrt(2.0 * G * x2)
            S3 += A3 * math.sqrt(2.0 * G * x3)
            S4 += A4 * math.sqrt(2.0 * G * x4)
            V1 += s['v1']
            V2 += s['v2']

        dh1 = tw[N - 1]['h1'] - tw[start]['h1']
        dh2 = tw[N - 1]['h2'] - tw[start]['h2']
        dh3 = tw[N - 1]['h3'] - tw[start]['h3']
        dh4 = tw[N - 1]['h4'] - tw[start]['h4']

        c1n = 0.8 * K1N
        c2n = 0.8 * K2N
        if V1 > 1.0:
            c1 = (dh4 + S4) / V1
        else:
            c1 = c1n
        if V2 > 1.0:
            c2 = (dh3 + S3) / V2
        else:
            c2 = c2n
        if c1 < 0.40 * c1n:
            c1 = 0.40 * c1n
        if c1 > 1.35 * c1n:
            c1 = 1.35 * c1n
        if c2 < 0.40 * c2n:
            c2 = 0.40 * c2n
        if c2 > 1.35 * c2n:
            c2 = 1.35 * c2n

        d1 = (dh1 + S1 - S3 - ALPHA * c1 * V1) / nw
        d2 = (dh2 + S2 - S4 - ALPHA * c2 * V2) / nw

        def predict(h2c):
            q2 = A2 * SQ2G * math.sqrt(h2c)
            q1 = Q_target - q2
            if q1 <= 1e-7:
                return None
            h1c = (q1 / A1) ** 2 / (2.0 * G)
            u1 = (ALPHA * q1 - q2 + d2 - ALPHA * d1) / (ALPHA * ALPHA - 1.0)
            u2 = (q2 - u1 - d2) / ALPHA
            return h1c, u1, u2

        qa = A1 * SQ2G * math.sqrt(h1a if h1a > 0.0 else 0.0) + A2 * SQ2G * math.sqrt(h2a if h2a > 0.0 else 0.0)
        if abs(qa - Q_target) < 1e-6:
            pa = predict(h2a)
            if pa is not None:
                hp1, up1, up2 = pa
                if up1 > 0.0 and up2 > 0.0:
                    h3p = (up2 / A3) ** 2 / (2.0 * G)
                    h4p = (up1 / A4) ** 2 / (2.0 * G)
                    v1p = up1 / c1
                    v2p = up2 / c2
                    if (h3p <= ulim - 0.015 and h4p <= ulim - 0.015
                            and h1a >= 0.03 and h1a <= 1.48
                            and h2a >= h2_lo - 0.005 and h2a <= h2_hi + 0.005
                            and v1p >= 1.2 and v1p <= 11.9
                            and v2p >= 1.2 and v2p <= 11.9):
                        return {'diagnosis': 'hold setpoints: predicted h3=%.3f h4=%.3f v1=%.2f v2=%.2f, Q on target' % (h3p, h4p, v1p, v2p),
                                'adjusted_setpoints': {'h1': h1a, 'h2': h2a}}

        soft3 = ulim - 0.04
        soft4 = ulim - 0.04
        b_lo = h2_lo + 0.012
        b_hi = h2_hi - 0.012

        lo2 = h2_lo - 0.06
        if lo2 < sp_lo:
            lo2 = sp_lo
        if lo2 < 0.07:
            lo2 = 0.07
        h2mx = (Q_target / (A2 * SQ2G)) ** 2 - 5e-4
        hi2 = h2_hi + 0.06
        if hi2 > sp_hi:
            hi2 = sp_hi
        if hi2 > h2mx:
            hi2 = h2mx
        if hi2 > 1.1:
            hi2 = 1.1
        if hi2 - lo2 < 1e-4:
            return {'diagnosis': 'no usable h2 range', 'adjusted_setpoints': fb}

        step = 0.0025
        kmx = int((hi2 - lo2) / step) + 1
        best_cost = None
        bh1 = h1a
        bh2 = h2a
        for k in range(kmx + 1):
            h2c = lo2 + k * step
            pr = predict(h2c)
            if pr is None:
                continue
            h1c, u1, u2 = pr
            if h1c < sp_lo or h1c > sp_hi:
                continue
            if u1 <= 0.0 or u2 <= 0.0:
                continue
            h3c = (u2 / A3) ** 2 / (2.0 * G)
            h4c = (u1 / A4) ** 2 / (2.0 * G)
            v1c = u1 / c1
            v2c = u2 / c2
            travel = abs(h1c - h1a) + abs(h2c - h2a)
            pen = 0.0
            if h3c > soft3:
                pen += 6000.0 * (h3c - soft3)
            if h4c > soft4:
                pen += 6000.0 * (h4c - soft4)
            if h2c > b_hi:
                pen += 8000.0 * (h2c - b_hi)
            if h2c < b_lo:
                pen += 8000.0 * (b_lo - h2c)
            if v1c > 11.5:
                pen += 500.0 * (v1c - 11.5)
            if v2c > 11.5:
                pen += 500.0 * (v2c - 11.5)
            if v1c < 1.3:
                pen += 500.0 * (1.3 - v1c)
            if v2c < 1.3:
                pen += 500.0 * (1.3 - v2c)
            if h1c > 1.45:
                pen += 40000.0 * (h1c - 1.45)
            if h1c < 0.045:
                pen += 40000.0 * (0.045 - h1c)
            cost = 100.0 * travel + pen
            if best_cost is None or cost < best_cost - 1e-12:
                best_cost = cost
                bh1 = h1c
                bh2 = h2c

        if bh1 < sp_lo:
            bh1 = sp_lo
        if bh1 > sp_hi:
            bh1 = sp_hi
        if bh2 < sp_lo:
            bh2 = sp_lo
        if bh2 > sp_hi:
            bh2 = sp_hi
        return {'diagnosis': 're-split production: h1=%.3f h2=%.3f (d1=%.2f L/s d2=%.2f L/s c1=%.5f c2=%.5f)' % (bh1, bh2, d1 * 1000.0, d2 * 1000.0, c1, c2),
                'adjusted_setpoints': {'h1': bh1, 'h2': bh2}}
    except Exception:
        return {'diagnosis': 'fallback on internal error', 'adjusted_setpoints': fb}
