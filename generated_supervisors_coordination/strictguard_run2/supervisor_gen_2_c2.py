def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1, a2, a3, a4 = 0.0035, 0.003, 0.002, 0.0025
    k1n, k2n = 0.00085, 0.00095
    g1, g2 = 0.20, 0.20
    sq2g = math.sqrt(2.0 * g)
    H1n, H2n = 0.30, 0.35
    P11n = g1 * k1n
    P12n = (1.0 - g1) * k1n
    P21n = (1.0 - g2) * k2n
    P22n = g2 * k2n
    QN = 1000.0 * (a1 * sq2g * math.sqrt(H1n) + a2 * sq2g * math.sqrt(H2n))

    sp_lo, sp_hi = objectives["setpoint_limits"]
    b_lo, b_hi = objectives["h2_band"]
    ulim = objectives["upper_level_limit"]
    Hlim = ulim - 0.02
    Qtarget = float(objectives["production_target"])
    sp1c = float(active_setpoints["h1"])
    sp2c = float(active_setpoints["h2"])

    scl = (Qtarget / QN) ** 2
    b1 = min(sp_hi, max(sp_lo, H1n * scl))
    b2 = min(sp_hi, max(sp_lo, H2n * scl))

    def fallback(msg):
        return {"diagnosis": msg, "adjusted_setpoints": {"h1": b1, "h2": b2}}

    try:
        W = telemetry_window
        if len(W) == 0:
            return fallback("empty window; nominal scaled setpoints")
        last = W[-1]
        h1 = float(last["h1"]); h2 = float(last["h2"])
        h3 = float(last["h3"]); h4 = float(last["h4"])
        v1 = float(last["v1"]); v2 = float(last["v2"])

        n = len(W)
        m = min(10, n)
        seg = W[n - m:]
        t0 = float(seg[0]["time"])
        xs = [float(ss["time"]) - t0 for ss in seg]

        def slope(key):
            ys = [float(ss[key]) for ss in seg]
            k = len(ys)
            sx = sum(xs)
            sy = sum(ys)
            sxx = sum(x * x for x in xs)
            sxy = sum(xs[i] * ys[i] for i in range(k))
            den = k * sxx - sx * sx
            if abs(den) < 1e-12:
                return 0.0
            return (k * sxy - sx * sy) / den

        dh1 = slope("h1"); dh2 = slope("h2")
        dh3 = slope("h3"); dh4 = slope("h4")

        sq1 = a1 * sq2g * math.sqrt(max(0.0, h1))
        sq2 = a2 * sq2g * math.sqrt(max(0.0, h2))
        sq3 = a3 * sq2g * math.sqrt(max(0.0, h3))
        sq4 = a4 * sq2g * math.sqrt(max(0.0, h4))

        if v2 > 0.6:
            P21e = (dh3 + sq3) / v2
        else:
            P21e = P21n
        if v1 > 0.6:
            P12e = (dh4 + sq4) / v1
        else:
            P12e = P12n
        P21e = min(max(P21e, 0.25 * P21n), 1.8 * P21n)
        P12e = min(max(P12e, 0.25 * P12n), 1.8 * P12n)
        P11e = P12e * (g1 / (1.0 - g1))
        P22e = P21e * (g2 / (1.0 - g2))

        d1e = dh1 + sq1 - sq3 - P11e * v1
        d2e = dh2 + sq2 - sq4 - P22e * v2

        det = P11e * P22e - P21e * P12e
        if abs(det) < 1e-15:
            return fallback("degenerate model; nominal scaled setpoints")

        ka1 = a1 * sq2g
        ka2 = a2 * sq2g
        kk3 = P21e / (a3 * sq2g)
        kk4 = P12e / (a4 * sq2g)
        Qm3 = Qtarget / 1000.0

        def predict(h1c):
            if h1c <= 1e-5:
                return None
            S1 = ka1 * math.sqrt(h1c)
            S2 = Qm3 - S1
            if S2 <= 1e-6:
                return None
            h2c = (S2 / ka2) ** 2
            x = S1 - d1e
            y = S2 - d2e
            v1c = (x * P22e - P21e * y) / det
            v2c = (P11e * y - P12e * x) / det
            h3c = (kk3 * max(v2c, 0.0)) ** 2
            h4c = (kk4 * max(v1c, 0.0)) ** 2
            return (h1c, h2c, v1c, v2c, h3c, h4c)

        def feasible(p):
            if p is None:
                return False
            h1c, h2c, v1c, v2c, h3c, h4c = p
            if h1c < sp_lo - 1e-9 or h1c > sp_hi + 1e-9:
                return False
            if h2c < sp_lo - 1e-9 or h2c > sp_hi + 1e-9:
                return False
            if h1c < 0.02 or h1c > 1.5 or h2c < 0.02 or h2c > 1.5:
                return False
            if h3c > Hlim or h4c > Hlim:
                return False
            if h2c < b_lo - 1e-9 or h2c > b_hi + 1e-9:
                return False
            if v1c < 1.2 or v1c > 11.8 or v2c < 1.2 or v2c > 11.8:
                return False
            return True

        pb = predict(b1)
        if feasible(pb):
            return {"diagnosis": "nominal split feasible h3=%.3f h4=%.3f v=%.1f/%.1f; no shift" % (pb[4], pb[5], pb[2], pb[3]),
                    "adjusted_setpoints": {"h1": b1, "h2": b2}}

        def cost(p):
            if p is None:
                return 1e18
            h1c, h2c, v1c, v2c, h3c, h4c = p
            c = 100.0 * (abs(h1c - sp1c) + abs(h2c - sp2c))
            if h1c < sp_lo or h1c > sp_hi or h2c < sp_lo or h2c > sp_hi:
                c += 1e6
            if h1c < 0.02 or h1c > 1.5 or h2c < 0.02 or h2c > 1.5:
                c += 1e7
            if h3c > Hlim:
                c += 900.0 * (h3c - Hlim)
            if h4c > Hlim:
                c += 900.0 * (h4c - Hlim)
            if h2c < b_lo:
                c += 900.0 * (b_lo - h2c)
            elif h2c > b_hi:
                c += 900.0 * (h2c - b_hi)
            else:
                if h2c > b_hi - 0.03:
                    c += 300.0 * (h2c - (b_hi - 0.03))
                if h2c < b_lo + 0.03:
                    c += 300.0 * ((b_lo + 0.03) - h2c)
            if v1c > 11.9:
                c += 3000.0 * (v1c - 11.9)
            elif v1c > 11.5:
                c += 400.0 * (v1c - 11.5)
            if v1c < 1.1:
                c += 3000.0 * (1.1 - v1c)
            elif v1c < 1.5:
                c += 400.0 * (1.5 - v1c)
            if v2c > 11.9:
                c += 3000.0 * (v2c - 11.9)
            elif v2c > 11.5:
                c += 400.0 * (v2c - 11.5)
            if v2c < 1.1:
                c += 3000.0 * (1.1 - v2c)
            elif v2c < 1.5:
                c += 400.0 * (1.5 - v2c)
            return c

        lo = max(sp_lo, 0.03)
        hi = min(sp_hi, 1.2)
        if hi - lo < 0.2:
            hi = min(sp_hi, 1.4)

        best_p = None
        best_c = None
        N1 = 80
        for i in range(N1 + 1):
            h1c = lo + (hi - lo) * i / N1
            p = predict(h1c)
            c = cost(p)
            if best_c is None or c < best_c:
                best_c = c
                best_p = p
        if best_p is not None:
            step = (hi - lo) / N1
            c0 = best_p[0]
            rlo = max(lo, c0 - step)
            rhi = min(hi, c0 + step)
            for i in range(61):
                h1c = rlo + (rhi - rlo) * i / 60.0
                p = predict(h1c)
                c = cost(p)
                if c < best_c:
                    best_c = c
                    best_p = p
        if pb is not None:
            cb = cost(pb)
            if best_p is None or cb < best_c:
                best_p = pb
                best_c = cb
        if best_p is None:
            return fallback("no feasible split found; nominal scaled setpoints")

        h1r = min(sp_hi, max(sp_lo, best_p[0]))
        h2r = min(sp_hi, max(sp_lo, best_p[1]))
        diag = ("shifted split; base (%.3f,%.3f) infeasible -> h1=%.3f h2=%.3f "
                "pred h3=%.3f h4=%.3f v1=%.1f v2=%.1f d1=%.4f d2=%.4f" %
                (b1, b2, h1r, h2r, best_p[4], best_p[5], best_p[2], best_p[3], d1e, d2e))
        return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1r, "h2": h2r}}
    except Exception:
        return fallback("fallback: nominal scaled setpoints")
