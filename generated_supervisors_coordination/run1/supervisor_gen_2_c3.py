def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1n = 0.00085
    k2n = 0.00095
    gam1 = 0.20
    gam2 = 0.20
    cc = math.sqrt(2.0 * 9.81)
    C1 = 1000.0 * a1 * cc
    C2 = 1000.0 * a2 * cc
    C3 = 1000.0 * a3 * cc
    C4 = 1000.0 * a4 * cc
    RAT = gam1 / (1.0 - gam1)
    DEN = 1.0 - RAT * RAT
    G1n = 1000.0 * (1.0 - gam1) * k1n
    G2n = 1000.0 * (1.0 - gam2) * k2n

    h1a = 0.30
    h2a = 0.35
    try:
        h1a = float(active_setpoints['h1'])
        h2a = float(active_setpoints['h2'])
    except Exception:
        h1a = 0.30
        h2a = 0.35

    try:
        Q_t = float(objectives['production_target'])
        band = objectives['h2_band']
        h2lo = float(band[0])
        h2hi = float(band[1])
        ulim = float(objectives['upper_level_limit'])
        lim = objectives['setpoint_limits']
        splo = float(lim[0])
        sphi = float(lim[1])
    except Exception:
        return {'diagnosis': 'fallback: objectives', 'adjusted_setpoints': {'h1': h1a, 'h2': h2a}}

    try:
        if ulim <= 0.0:
            ulim = 0.75
        if Q_t <= 0.0:
            Q_t = 0.001

        n = len(telemetry_window)
        m = 15
        if n < m:
            m = n
        if m < 2:
            return {'diagnosis': 'fallback: short window', 'adjusted_setpoints': {'h1': h1a, 'h2': h2a}}
        tail = telemetry_window[n - m:]

        def fit(key):
            vals = []
            for row in tail:
                vals.append(float(row[key]))
            mm = len(vals)
            if mm < 2:
                return vals[0], 0.0
            mt = (mm - 1) * 0.5
            num = 0.0
            den = 0.0
            s = 0.0
            for i in range(mm):
                d = i - mt
                num += d * vals[i]
                den += d * d
                s += vals[i]
            sl = num / den if den > 0.0 else 0.0
            mean = s / mm
            return mean + sl * (mm - 1 - mt), sl

        h1, sh1 = fit('h1')
        h2, sh2 = fit('h2')
        h3, sh3 = fit('h3')
        h4, sh4 = fit('h4')
        v1, sv1 = fit('v1')
        v2, sv2 = fit('v2')

        if h1 < 0.0:
            h1 = 0.0
        if h2 < 0.0:
            h2 = 0.0
        if h3 < 0.0:
            h3 = 0.0
        if h4 < 0.0:
            h4 = 0.0

        r1 = math.sqrt(h1)
        r2 = math.sqrt(h2)
        r3 = math.sqrt(h3)
        r4 = math.sqrt(h4)

        A3m = C3 * r3 + 1000.0 * sh3
        A4m = C4 * r4 + 1000.0 * sh4

        D1 = 1000.0 * sh1 + C1 * r1 - C3 * r3 - RAT * A4m
        D2 = 1000.0 * sh2 + C2 * r2 - C4 * r4 - RAT * A3m

        G1e = G1n
        G2e = G2n
        if v1 > 1.0:
            G1e = A4m / v1
        if v2 > 1.0:
            G2e = A3m / v2
        if G1e < 0.45 * G1n:
            G1e = 0.45 * G1n
        if G1e > 1.60 * G1n:
            G1e = 1.60 * G1n
        if G2e < 0.45 * G2n:
            G2e = 0.45 * G2n
        if G2e > 1.60 * G2n:
            G2e = 1.60 * G2n
        if D1 > 8.0:
            D1 = 8.0
        if D1 < -8.0:
            D1 = -8.0
        if D2 > 8.0:
            D2 = 8.0
        if D2 < -8.0:
            D2 = -8.0

        ulim_p = ulim
        if h3 > ulim - 0.06 and sh3 > 0.0002:
            ulim_p = ulim - 0.02
        if h4 > ulim - 0.06 and sh4 > 0.0002 and ulim_p > ulim - 0.02:
            ulim_p = ulim - 0.02
        if ulim_p < 0.20:
            ulim_p = 0.20

        Q1n = Q_t * 0.51932
        Q2n = Q_t - Q1n
        if Q2n < 0.0:
            Q2n = 0.0
        h1n = (Q1n / C1) ** 2 if Q1n > 0.0 else 0.0
        h2n = (Q2n / C2) ** 2 if Q2n > 0.0 else 0.0

        h1_lo = 0.25 * h1n
        h1_hi = 2.00 * h1n
        h2_lo = 0.25 * h2n
        h2_hi = 2.00 * h2n
        if h1_lo < 0.04:
            h1_lo = 0.04
        if h2_lo < 0.04:
            h2_lo = 0.04
        if h1_lo < splo:
            h1_lo = splo
        if h2_lo < splo:
            h2_lo = splo
        if h1_hi > sphi:
            h1_hi = sphi
        if h2_hi > sphi:
            h2_hi = sphi
        if h1_hi > 1.45:
            h1_hi = 1.45
        if h2_hi > 1.45:
            h2_hi = 1.45
        if h1_lo < 0.02:
            h1_lo = 0.02
        if h2_lo < 0.02:
            h2_lo = 0.02
        if h1_hi < h1_lo + 0.01:
            h1_hi = h1_lo + 0.01
        if h2_hi < h2_lo + 0.01:
            h2_hi = h2_lo + 0.01

        def costf(h1s, h2s):
            if h1s <= 0.0 or h2s <= 0.0:
                return 1.0e9
            q1 = C1 * math.sqrt(h1s)
            q2 = C2 * math.sqrt(h2s)
            A3 = (q1 - D1 - RAT * (q2 - D2)) / DEN
            A4 = (q2 - D2 - RAT * (q1 - D1)) / DEN
            pen = 0.0
            if A3 < 0.0:
                pen += 400.0 + 200.0 * (-A3) / 0.005
                A3 = 0.0
            if A4 < 0.0:
                pen += 400.0 + 200.0 * (-A4) / 0.005
                A4 = 0.0
            h3s = (A3 / C3) ** 2
            h4s = (A4 / C4) ** 2
            e = h3s - ulim_p
            if e > 0.0:
                pen += 200.0 * (e / 0.05 if e < 0.05 else 1.0)
            e = h4s - ulim_p
            if e > 0.0:
                pen += 200.0 * (e / 0.05 if e < 0.05 else 1.0)
            e = h3s - (ulim_p - 0.05)
            if e > 0.0:
                pen += 6.0 * (e / 0.05 if e < 0.05 else 1.0)
            e = h4s - (ulim_p - 0.05)
            if e > 0.0:
                pen += 6.0 * (e / 0.05 if e < 0.05 else 1.0)
            e = h2s - h2hi
            if e > 0.0:
                pen += 200.0 * (e / 0.05 if e < 0.05 else 1.0)
            e = h2lo - h2s
            if e > 0.0:
                pen += 200.0 * (e / 0.05 if e < 0.05 else 1.0)
            e = h2s - (h2hi - 0.02)
            if e > 0.0:
                pen += 4.0 * (e / 0.02 if e < 0.02 else 1.0)
            e = (h2lo + 0.02) - h2s
            if e > 0.0:
                pen += 4.0 * (e / 0.02 if e < 0.02 else 1.0)
            vs1 = A4 / G1e
            vs2 = A3 / G2e
            if vs1 > 11.8:
                pen += 200.0 * (vs1 - 11.8)
            if vs1 < 1.2:
                pen += 200.0 * (1.2 - vs1)
            if vs2 > 11.8:
                pen += 200.0 * (vs2 - 11.8)
            if vs2 < 1.2:
                pen += 200.0 * (1.2 - vs2)
            pen += 100.0 * abs(q1 + q2 - Q_t)
            pen += 100.0 * (abs(h1s - h1a) + abs(h2s - h2a))
            if h1s < 0.06:
                pen += 300.0 * (0.06 - h1s)
            if h2s < 0.06:
                pen += 300.0 * (0.06 - h2s)
            return pen

        best_c = costf(h1a, h2a)
        best_h1 = h1a
        best_h2 = h2a

        NGRID = 48
        st1 = (h1_hi - h1_lo) / NGRID
        st2 = (h2_hi - h2_lo) / NGRID
        i = 0
        while i <= NGRID:
            h1s = h1_lo + i * st1
            j = 0
            while j <= NGRID:
                h2s = h2_lo + j * st2
                cval = costf(h1s, h2s)
                if cval < best_c:
                    best_c = cval
                    best_h1 = h1s
                    best_h2 = h2s
                j += 1
            i += 1

        s1 = st1
        s2 = st2
        kk = 0
        while kk < 6:
            base_h1 = best_h1
            base_h2 = best_h2
            di = -3
            while di <= 3:
                h1s = base_h1 + di * s1
                if h1s >= h1_lo and h1s <= h1_hi:
                    dj = -3
                    while dj <= 3:
                        h2s = base_h2 + dj * s2
                        if h2s >= h2_lo and h2s <= h2_hi:
                            cval = costf(h1s, h2s)
                            if cval < best_c:
                                best_c = cval
                                best_h1 = h1s
                                best_h2 = h2s
                        dj += 1
                di += 1
            s1 *= 0.45
            s2 *= 0.45
            kk += 1

        lo_b = splo
        if lo_b < 0.02:
            lo_b = 0.02
        hi_b = sphi
        if hi_b > 1.5:
            hi_b = 1.5
        if hi_b < lo_b:
            hi_b = lo_b
        if best_h1 < lo_b:
            best_h1 = lo_b
        if best_h1 > hi_b:
            best_h1 = hi_b
        if best_h2 < lo_b:
            best_h2 = lo_b
        if best_h2 > hi_b:
            best_h2 = hi_b

        q1 = C1 * math.sqrt(best_h1)
        q2 = C2 * math.sqrt(best_h2)
        A3 = (q1 - D1 - RAT * (q2 - D2)) / DEN
        A4 = (q2 - D2 - RAT * (q1 - D1)) / DEN
        if A3 < 0.0:
            A3 = 0.0
        if A4 < 0.0:
            A4 = 0.0
        h3p = (A3 / C3) ** 2
        h4p = (A4 / C4) ** 2
        v1p = A4 / G1e
        v2p = A3 / G2e
        diag = 'sp=(%.3f,%.3f) D=(%.2f,%.2f) G=(%.3f,%.3f) h3p=%.2f h4p=%.2f vp=(%.1f,%.1f) Q=%.2f' % (
            best_h1, best_h2, D1, D2, G1e, G2e, h3p, h4p, v1p, v2p, q1 + q2)
        return {'diagnosis': diag, 'adjusted_setpoints': {'h1': best_h1, 'h2': best_h2}}
    except Exception:
        return {'diagnosis': 'fallback: exception', 'adjusted_setpoints': {'h1': h1a, 'h2': h2a}}
