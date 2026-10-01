def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    g1 = 0.20
    g2 = 0.20
    c = math.sqrt(2.0 * 9.81)

    h1a = 0.30
    h2a = 0.35
    try:
        h1a = float(active_setpoints["h1"])
        h2a = float(active_setpoints["h2"])
    except Exception:
        pass
    held = {"diagnosis": "hold setpoints", "adjusted_setpoints": {"h1": h1a, "h2": h2a}}

    try:
        Q_t = float(objectives["production_target"])
        band = objectives["h2_band"]
        h2blo = float(band[0])
        h2bhi = float(band[1])
        ulim = float(objectives["upper_level_limit"])
        lim = objectives["setpoint_limits"]
        splo = float(lim[0])
        sphi = float(lim[1])

        n = len(telemetry_window)
        if n < 6:
            return held
        m = 16
        if n < m:
            m = n
        tail = telemetry_window[n - m:]

        def fit(sig):
            vals = []
            for row in tail:
                vals.append(float(row[sig]))
            mm = len(vals)
            mt = (mm - 1) * 0.5
            num = 0.0
            den = 0.0
            sm = 0.0
            for i in range(mm):
                dd = i - mt
                num += dd * vals[i]
                sm += vals[i]
                den += dd * dd
            if den <= 0.0:
                return vals[mm - 1], 0.0
            sl = num / den
            return sm / mm + sl * (mm - 1 - mt), sl

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

        sq = math.sqrt
        F1 = (a4 * c * sq(h4) + sh4) / (1.0 - g1)
        F2 = (a3 * c * sq(h3) + sh3) / (1.0 - g2)
        if F1 < 1e-7:
            F1 = 1e-7
        if F2 < 1e-7:
            F2 = 1e-7
        d1 = a1 * c * sq(h1) + sh1 - (1.0 - g2) * F2 - g1 * F1
        d2 = a2 * c * sq(h2) + sh2 - (1.0 - g1) * F1 - g2 * F2
        if d1 > 0.005:
            d1 = 0.005
        if d1 < -0.005:
            d1 = -0.005
        if d2 > 0.005:
            d2 = 0.005
        if d2 < -0.005:
            d2 = -0.005

        ke1 = k1
        ke2 = k2
        if v1 > 0.5:
            ke1 = F1 / v1
        if v2 > 0.5:
            ke2 = F2 / v2
        if ke1 < 0.55 * k1:
            ke1 = 0.55 * k1
        if ke1 > 1.15 * k1:
            ke1 = 1.15 * k1
        if ke2 < 0.55 * k2:
            ke2 = 0.55 * k2
        if ke2 > 1.15 * k2:
            ke2 = 1.15 * k2

        det = 1.0 - g1 - g2
        if det < 0.05:
            det = 0.05

        def predict(h1s, h2s):
            A = a1 * c * sq(h1s)
            B = a2 * c * sq(h2s)
            Fa = A - d1
            Fb = B - d2
            F2p = ((1.0 - g1) * Fa - g1 * Fb) / det
            F1p = ((1.0 - g2) * Fb - g2 * Fa) / det
            if F2p < 0.0:
                F2p = 0.0
            if F1p < 0.0:
                F1p = 0.0
            h3p = ((1.0 - g2) * F2p / (a3 * c)) ** 2
            h4p = ((1.0 - g1) * F1p / (a4 * c)) ** 2
            v1p = F1p / ke1
            v2p = F2p / ke2
            return h3p, h4p, v1p, v2p

        ul_s = ulim * 0.95
        if ul_s > ulim - 0.02:
            ul_s = ulim - 0.02
        if ul_s < 0.0:
            ul_s = 0.0
        h2b_lo_m = h2blo + 0.005
        h2b_hi_m = h2bhi - 0.005
        if h2b_hi_m <= h2b_lo_m:
            h2b_lo_m = h2blo
            h2b_hi_m = h2bhi
        vhi = 11.8
        vlo = 1.3

        def feasible(h1s, h2s):
            h3p, h4p, v1p, v2p = predict(h1s, h2s)
            if h3p > ul_s or h4p > ul_s:
                return False
            if h2s > h2b_hi_m or h2s < h2b_lo_m:
                return False
            if v1p > vhi or v1p < vlo:
                return False
            if v2p > vhi or v2p < vlo:
                return False
            Qp = 1000.0 * (a1 * c * sq(h1s) + a2 * c * sq(h2s))
            if abs(Qp - Q_t) > 0.2:
                return False
            return True

        def penalty(h1s, h2s):
            h3p, h4p, v1p, v2p = predict(h1s, h2s)
            p = 0.0
            if h3p > ul_s:
                p += h3p - ul_s
            if h4p > ul_s:
                p += h4p - ul_s
            if h2s > h2b_hi_m:
                p += h2s - h2b_hi_m
            if h2s < h2b_lo_m:
                p += h2b_lo_m - h2s
            if v1p > vhi:
                p += 0.03 * (v1p - vhi)
            if v1p < vlo:
                p += 0.03 * (vlo - v1p)
            if v2p > vhi:
                p += 0.03 * (v2p - vhi)
            if v2p < vlo:
                p += 0.03 * (vlo - v2p)
            Qp = 1000.0 * (a1 * c * sq(h1s) + a2 * c * sq(h2s))
            p += 0.05 * abs(Qp - Q_t)
            return p

        h1_lo = splo
        if h1_lo < 0.02:
            h1_lo = 0.02
        h1_hi = sphi
        if h1_hi > 1.5:
            h1_hi = 1.5
        h2_lo = splo
        if h2_lo < 0.02:
            h2_lo = 0.02
        h2_hi = sphi
        if h2_hi > 1.5:
            h2_hi = 1.5

        a1c = 1000.0 * a1 * c
        a2c = 1000.0 * a2 * c
        q1_lo = a1c * sq(h1_lo)
        q1_hi = a1c * sq(h1_hi)
        q2_lo = a2c * sq(h2_lo)
        q2_hi = a2c * sq(h2_hi)
        lo = q1_lo
        t = Q_t - q2_hi
        if t > lo:
            lo = t
        hi = q1_hi
        t = Q_t - q2_lo
        if t < hi:
            hi = t
        if lo < 0.0:
            lo = 0.0
        if hi > Q_t:
            hi = Q_t
        if hi < lo:
            lo = q1_lo
            hi = q1_hi
            if lo < 0.0:
                lo = 0.0
            if hi > Q_t:
                hi = Q_t
            if hi < lo:
                return held

        best_feas_h1 = None
        best_feas_h2 = None
        best_feas_travel = 1e18
        best_inf_h1 = None
        best_inf_h2 = None
        best_inf_pen = 1e18

        active_ok = (h1a >= h1_lo and h1a <= h1_hi and h2a >= h2_lo and h2a <= h2_hi)

        def consider(ch1, ch2):
            nonlocal_state = None
            return ch1, ch2

        cands = []
        if active_ok:
            cands.append((h1a, h2a))
        npts = 200
        span = hi - lo
        if span < 0.0:
            span = 0.0
        for i in range(npts + 1):
            if npts > 0:
                q1 = lo + span * i / npts
            else:
                q1 = lo
            q2 = Q_t - q1
            if q2 < 0.0:
                continue
            ch1 = (q1 / a1c) ** 2
            ch2 = (q2 / a2c) ** 2
            if ch1 < h1_lo or ch1 > h1_hi:
                continue
            if ch2 < h2_lo or ch2 > h2_hi:
                continue
            cands.append((ch1, ch2))

        for pair in cands:
            ch1 = pair[0]
            ch2 = pair[1]
            travel = abs(ch1 - h1a) + abs(ch2 - h2a)
            if feasible(ch1, ch2):
                if travel < best_feas_travel:
                    best_feas_travel = travel
                    best_feas_h1 = ch1
                    best_feas_h2 = ch2
            else:
                pen = penalty(ch1, ch2)
                if pen < best_inf_pen:
                    best_inf_pen = pen
                    best_inf_h1 = ch1
                    best_inf_h2 = ch2

        if best_feas_h1 is not None:
            best_h1 = best_feas_h1
            best_h2 = best_feas_h2
        elif best_inf_h1 is not None:
            best_h1 = best_inf_h1
            best_h2 = best_inf_h2
        else:
            return held

        if best_h1 < h1_lo:
            best_h1 = h1_lo
        if best_h1 > h1_hi:
            best_h1 = h1_hi
        if best_h2 < h2_lo:
            best_h2 = h2_lo
        if best_h2 > h2_hi:
            best_h2 = h2_hi

        h3p, h4p, v1p, v2p = predict(best_h1, best_h2)
        diag = "d1=%+.2f d2=%+.2f L/s k=%0.2f/%0.2f sp=%.3f/%.3f h3=%.2f h4=%.2f v=%.1f/%.1f" % (
            1000.0 * d1, 1000.0 * d2, ke1 / k1, ke2 / k2,
            best_h1, best_h2, h3p, h4p, v1p, v2p)
        return {"diagnosis": diag, "adjusted_setpoints": {"h1": best_h1, "h2": best_h2}}
    except Exception:
        return held
