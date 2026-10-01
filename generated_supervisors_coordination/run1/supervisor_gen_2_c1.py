def supervise(telemetry_window, active_setpoints, objectives):
    try:
        h1a = float(active_setpoints["h1"])
        h2a = float(active_setpoints["h2"])
    except Exception:
        h1a = 0.30
        h2a = 0.35
    fallback = {"diagnosis": "hold setpoints", "adjusted_setpoints": {"h1": h1a, "h2": h2a}}
    try:
        a1 = 0.0035
        a2 = 0.003
        a3 = 0.002
        a4 = 0.0025
        k1 = 0.00085
        k2 = 0.00095
        c = math.sqrt(2.0 * 9.81)
        f1 = 1000.0 * a1 * c
        f2 = 1000.0 * a2 * c
        f3 = 1000.0 * a3 * c
        f4 = 1000.0 * a4 * c
        g3n = 1000.0 * 0.8 * k2
        g4n = 1000.0 * 0.8 * k1
        q1ref = f1 * math.sqrt(0.30)
        q2ref = f2 * math.sqrt(0.35)
        r1 = q1ref / (q1ref + q2ref)

        Q_t = float(objectives["production_target"])
        band = objectives["h2_band"]
        h2blo = float(band[0])
        h2bhi = float(band[1])
        ulim = float(objectives["upper_level_limit"])
        lim = objectives["setpoint_limits"]
        splo = float(lim[0])
        sphi = float(lim[1])
        if Q_t <= 0.0:
            return fallback

        n = len(telemetry_window)
        if n < 6:
            return fallback
        m = 20
        if m > n:
            m = n
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
                dd = i - mt
                num += dd * vals[i]
                den += dd * dd
                s += vals[i]
            sl = num / den if den > 0.0 else 0.0
            a0 = s / mm - sl * mt
            return a0 + sl * (mm - 1), sl

        h1, sh1 = fit("h1")
        h2, sh2 = fit("h2")
        h3, sh3 = fit("h3")
        h4, sh4 = fit("h4")
        v1, sv1 = fit("v1")
        v2, sv2 = fit("v2")
        if h1 < 0.0:
            h1 = 0.0
        if h2 < 0.0:
            h2 = 0.0
        if h3 < 0.0:
            h3 = 0.0
        if h4 < 0.0:
            h4 = 0.0

        # lower-tank outflows and upper-tank outflows (L/s)
        q1c = f1 * math.sqrt(h1)
        q2c = f2 * math.sqrt(h2)
        out3 = f3 * math.sqrt(h3)
        out4 = f4 * math.sqrt(h4)
        # pump-side streams into the upper tanks (L/s)
        P3 = out3 + 1000.0 * sh3
        P4 = out4 + 1000.0 * sh4
        if P3 < 0.0:
            P3 = 0.0
        if P4 < 0.0:
            P4 = 0.0
        # disturbance = lower-tank imbalance minus direct pump flow (0.25 = g/(1-g))
        d1 = q1c + 1000.0 * sh1 - out3 - 0.25 * P4
        d2 = q2c + 1000.0 * sh2 - out4 - 0.25 * P3
        if d1 > 4.0:
            d1 = 4.0
        if d1 < -4.0:
            d1 = -4.0
        if d2 > 4.0:
            d2 = 4.0
        if d2 < -4.0:
            d2 = -4.0

        # effective pump-side gains (L/(s*V)) from measured pump streams
        if v2 > 0.5:
            c3e = P3 / (1000.0 * v2)
        else:
            c3e = g3n
        if v1 > 0.5:
            c4e = P4 / (1000.0 * v1)
        else:
            c4e = g4n
        if c3e > 1.6 * g3n:
            c3e = 1.6 * g3n
        if c3e < 0.4 * g3n:
            c3e = 0.4 * g3n
        if c4e > 1.6 * g4n:
            c4e = 1.6 * g4n
        if c4e < 0.4 * g4n:
            c4e = 0.4 * g4n

        # nominal target split (same production ratio as the design point)
        Q1n = Q_t * r1
        Q2n = Q_t - Q1n

        # soft upper-level target
        h3t = ulim - 0.06
        if h3t > 0.94 * ulim:
            h3t = 0.94 * ulim
        if h3t < 0.35:
            h3t = 0.35
        h4t = h3t

        # hard level limits
        h1lo = 0.03
        if splo > h1lo:
            h1lo = splo
        h1hi = 1.40
        if sphi < h1hi:
            h1hi = sphi
        h2lo = 0.03
        if splo > h2lo:
            h2lo = splo
        h2hi = 1.40
        if sphi < h2hi:
            h2hi = sphi

        # feasible interval for the production shift delta (Q1 = Q1n - delta)
        dlo = Q1n - f1 * math.sqrt(h1hi)
        dhi = Q1n - f1 * math.sqrt(h1lo)
        t = f2 * math.sqrt(h2lo) - Q2n
        if t > dlo:
            dlo = t
        t = f2 * math.sqrt(h2hi) - Q2n
        if t < dhi:
            dhi = t
        t = Q1n - 0.2
        if t < dhi:
            dhi = t
        t = 0.2 - Q2n
        if t > dlo:
            dlo = t
        if dlo > dhi:
            return fallback

        nst = 60
        bestJ = None
        bestd = 0.0
        w_ulim = 30.0
        w_band = 30.0
        w_pump = 60.0
        w_safe = 2000.0
        vmax = 11.6
        vmin = 1.3
        for i in range(nst + 1):
            dd = dlo + (dhi - dlo) * i / nst
            Q1 = Q1n - dd
            Q2 = Q2n + dd
            h1s = (Q1 / f1) ** 2
            h2s = (Q2 / f2) ** 2
            W3 = (4.0 * (Q1 - d1) - (Q2 - d2)) / 3.75
            W4 = (4.0 * (Q2 - d2) - (Q1 - d1)) / 3.75
            if W3 < 0.0:
                W3 = 0.0
            if W4 < 0.0:
                W4 = 0.0
            h3p = (W3 / f3) ** 2
            h4p = (W4 / f4) ** 2
            v2p = W3 / (1000.0 * c3e)
            v1p = W4 / (1000.0 * c4e)
            J = abs(h1s - h1a) + abs(h2s - h2a)
            if h3p > h3t:
                J += w_ulim * (h3p - h3t)
            if h4p > h4t:
                J += w_ulim * (h4p - h4t)
            if h2s > h2bhi:
                J += w_band * (h2s - h2bhi)
            if h2s < h2blo:
                J += w_band * (h2blo - h2s)
            if v2p > vmax:
                J += w_pump * (v2p - vmax)
            if v2p < vmin:
                J += w_pump * (vmin - v2p)
            if v1p > vmax:
                J += w_pump * (v1p - vmax)
            if v1p < vmin:
                J += w_pump * (vmin - v1p)
            if h1s > h1hi:
                J += w_safe * (h1s - h1hi)
            if h1s < h1lo:
                J += w_safe * (h1lo - h1s)
            if h2s > h2hi:
                J += w_safe * (h2s - h2hi)
            if h2s < h2lo:
                J += w_safe * (h2lo - h2s)
            if bestJ is None or J < bestJ:
                bestJ = J
                bestd = dd

        if bestJ is None:
            return fallback

        dfin = bestd
        Q1s = Q1n - dfin
        Q2s = Q_t - Q1s
        if Q1s < 0.2:
            Q1s = 0.2
            Q2s = Q_t - 0.2
        if Q2s < 0.2:
            Q2s = 0.2
            Q1s = Q_t - 0.2
        h1s = (Q1s / f1) ** 2
        h2s = (Q2s / f2) ** 2
        if h1s < splo:
            h1s = splo
        if h1s > sphi:
            h1s = sphi
        if h2s < splo:
            h2s = splo
        if h2s > sphi:
            h2s = sphi
        if abs(h1s - h1a) < 0.0015 and abs(h2s - h2a) < 0.0015:
            h1s = h1a
            h2s = h2a

        W3f = (4.0 * (Q1s - d1) - (Q2s - d2)) / 3.75
        W4f = (4.0 * (Q2s - d2) - (Q1s - d1)) / 3.75
        if W3f < 0.0:
            W3f = 0.0
        if W4f < 0.0:
            W4f = 0.0
        h3f = (W3f / f3) ** 2
        h4f = (W4f / f4) ** 2
        v1f = W4f / (1000.0 * c4e)
        v2f = W3f / (1000.0 * c3e)
        diag = ("Qt=%.2f d=%+.2f d1=%+.2f d2=%+.2f h3p=%.2f h4p=%.2f vp=%.1f/%.1f"
                % (Q_t, dfin, d1, d2, h3f, h4f, v1f, v2f))
        return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1s, "h2": h2s}}
    except Exception:
        return fallback
