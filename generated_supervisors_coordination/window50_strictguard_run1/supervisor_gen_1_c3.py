def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    A1 = 0.0035
    A2 = 0.0030
    A3 = 0.0020
    A4 = 0.0025
    G1N = 0.00017
    U1N = 0.00068
    G2N = 0.00019
    U2N = 0.00076

    h1c = 0.30
    h2c = 0.35
    try:
        h1c = float(active_setpoints["h1"])
        h2c = float(active_setpoints["h2"])
    except Exception:
        h1c = 0.30
        h2c = 0.35

    try:
        target = float(objectives["production_target"])
        band = objectives["h2_band"]
        blo = float(band[0])
        bhi = float(band[1])
        hlim = float(objectives["upper_level_limit"])
        lims = objectives["setpoint_limits"]
        slo = float(lims[0])
        shi = float(lims[1])

        n = len(telemetry_window)
        sN = telemetry_window[n - 1]
        v1 = float(sN["v1"])
        v2 = float(sN["v2"])
        h1m = float(sN["h1"])
        h2m = float(sN["h2"])
        h3m = float(sN["h3"])
        h4m = float(sN["h4"])
        v1s = max(v1, 0.5)
        v2s = max(v2, 0.5)

        def oflow(h):
            if h < 0.0:
                h = 0.0
            return math.sqrt(2.0 * g * h)

        idx = n - 11
        if idx < 0:
            idx = 0
        sP = telemetry_window[idx]
        dt = float(sN["time"]) - float(sP["time"])
        if dt <= 0.0:
            dt = 1.0
        h3p = float(sP["h3"])
        h4p = float(sP["h4"])
        v1p = float(sP["v1"])
        v2p = float(sP["v2"])

        U1 = A4 * oflow(h4m) / v1s
        U2 = A3 * oflow(h3m) / v2s
        U1d = ((h4m - h4p) / dt + A4 * oflow(0.5 * (h4m + h4p))) / max(0.5 * (v1 + v1p), 0.5)
        U2d = ((h3m - h3p) / dt + A3 * oflow(0.5 * (h3m + h3p))) / max(0.5 * (v2 + v2p), 0.5)
        if U1d > U1:
            U1 = U1d
        if U2d > U2:
            U2 = U2d
        U1 = min(max(U1, 0.0001), 0.003)
        U2 = min(max(U2, 0.0001), 0.003)

        F1m = A1 * oflow(h1m)
        F2m = A2 * oflow(h2m)
        G1 = (F1m - U2 * v2) / v1s
        G2 = (F2m - U1 * v1) / v2s
        G1 = min(max(G1, 0.00001), 0.002)
        G2 = min(max(G2, 0.00001), 0.002)

        det = G1 * G2 - U1 * U2
        if not (det < -1.0e-10):
            G1 = G1N
            U1 = U1N
            G2 = G2N
            U2 = U2N
            det = G1 * G2 - U1 * U2

        Qm = 0.001 * target

        def pred(F1, F2):
            pv1 = (F1 * G2 - U2 * F2) / det
            pv2 = (G1 * F2 - U1 * F1) / det
            ph3 = 0.0
            ph4 = 0.0
            if pv2 > 0.0:
                t = U2 * pv2 / A3
                ph3 = t * t / (2.0 * g)
            if pv1 > 0.0:
                t = U1 * pv1 / A4
                ph4 = t * t / (2.0 * g)
            return pv1, pv2, ph3, ph4

        up_th = hlim - 0.01
        bh_th = bhi - 0.005
        bl_th = blo + 0.005
        v_hi = 11.8
        v_lo = 1.0

        def viol_pen(pv1, pv2, ph3, ph4, ch2):
            c = 0.0
            if ph3 > up_th:
                c += 300.0 * (ph3 - up_th)
            if ph4 > up_th:
                c += 300.0 * (ph4 - up_th)
            if ch2 > bh_th:
                c += 300.0 * (ch2 - bh_th)
            if ch2 < bl_th:
                c += 300.0 * (bl_th - ch2)
            if pv1 > v_hi:
                c += 120.0 * (pv1 - v_hi)
            if pv1 < v_lo:
                c += 120.0 * (v_lo - pv1)
            if pv2 > v_hi:
                c += 120.0 * (pv2 - v_hi)
            if pv2 < v_lo:
                c += 120.0 * (v_lo - pv2)
            return c

        best_h1 = h1c
        best_h2 = h2c
        best_cost = None

        h1 = 0.08
        while h1 <= 1.0001:
            F1 = A1 * oflow(h1)
            F2 = Qm - F1
            if F2 > 0.0001:
                h2 = (F2 / A2) * (F2 / A2) / (2.0 * g)
                if h2 >= 0.06 and h2 <= 1.2:
                    pv1, pv2, ph3, ph4 = pred(F1, F2)
                    if pv1 == pv1 and pv2 == pv2 and ph3 == ph3 and ph4 == ph4:
                        c = 100.0 * (abs(h1 - h1c) + abs(h2 - h2c))
                        c += 25.0 * abs((F1 + F2) * 1000.0 - target)
                        c += viol_pen(pv1, pv2, ph3, ph4, h2)
                        if best_cost is None or c < best_cost:
                            best_cost = c
                            best_h1 = h1
                            best_h2 = h2
            h1 += 0.002

        Fc1 = A1 * oflow(h1c)
        Fc2 = A2 * oflow(h2c)
        pv1, pv2, ph3, ph4 = pred(Fc1, Fc2)
        if pv1 == pv1 and pv2 == pv2:
            c = 25.0 * abs((Fc1 + Fc2) * 1000.0 - target)
            c += viol_pen(pv1, pv2, ph3, ph4, h2c)
            if best_cost is None or c < best_cost:
                best_cost = c
                best_h1 = h1c
                best_h2 = h2c

        nh1 = best_h1
        nh2 = best_h2
        if abs(nh1 - h1c) + abs(nh2 - h2c) < 0.006:
            nh1 = h1c
            nh2 = h2c
        d1 = nh1 - h1c
        d2 = nh2 - h2c
        if d1 > 0.25:
            d1 = 0.25
        if d1 < -0.25:
            d1 = -0.25
        if d2 > 0.25:
            d2 = 0.25
        if d2 < -0.25:
            d2 = -0.25
        nh1 = min(shi, max(slo, h1c + d1))
        nh2 = min(shi, max(slo, h2c + d2))
        nh1 = min(1.40, max(0.04, nh1))
        nh2 = min(1.40, max(0.04, nh2))

        Fn1 = A1 * oflow(nh1)
        Fn2 = A2 * oflow(nh2)
        pv1, pv2, ph3, ph4 = pred(Fn1, Fn2)
        diag = ("split for Q=%.2f L/s: sp (%.3f,%.3f)->(%.3f,%.3f); "
                "model h3=%.3f h4=%.3f v=(%.2f,%.2f); "
                "est G=(%.5f,%.5f) U=(%.5f,%.5f)") % (
            target, h1c, h2c, nh1, nh2, ph3, ph4, pv1, pv2, G1, G2, U1, U2)
        return {
            "diagnosis": diag,
            "adjusted_setpoints": {"h1": nh1, "h2": nh2},
        }
    except Exception:
        return {
            "diagnosis": "fallback: hold setpoints",
            "adjusted_setpoints": {"h1": h1c, "h2": h2c},
        }
