def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    S2 = (2.0 * g) ** 0.5
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    gam1 = 0.20
    gam2 = 0.20
    A1n = (1.0 - gam1) * 0.00085
    A2n = (1.0 - gam2) * 0.00095

    h1_fb = 0.30
    h2_fb = 0.35
    try:
        h1_fb = float(active_setpoints["h1"])
        h2_fb = float(active_setpoints["h2"])
    except Exception:
        pass

    try:
        W = telemetry_window
        n = len(W)
        last = W[n - 1]

        lo_lim = objectives["setpoint_limits"][0]
        hi_lim = objectives["setpoint_limits"][1]
        Q = objectives["production_target"] / 1000.0
        h2_lo = objectives["h2_band"][0]
        h2_hi = objectives["h2_band"][1]
        ulim = objectives["upper_level_limit"]

        def qh(h, a):
            if h <= 0.0:
                return 0.0
            return a * ((2.0 * g * h) ** 0.5)

        def hq(q, a):
            if q <= 0.0:
                return 0.0
            r = q / (a * S2)
            return r * r

        h1_cur = min(hi_lim, max(lo_lim, h1_fb))
        h2_cur = min(hi_lim, max(lo_lim, h2_fb))

        # ---------- least-squares level slopes over the last samples ----------
        m = 15
        if m > n:
            m = n
        base = n - m
        s0 = float(m)
        s1 = 0.0
        s2 = 0.0
        for i in range(m):
            x = float(i)
            s1 += x
            s2 += x * x
        den = s0 * s2 - s1 * s1
        if den == 0.0:
            den = 1.0

        def slope(key):
            sy = 0.0
            sxy = 0.0
            for i in range(m):
                x = float(i)
                y = W[base + i][key]
                sy += y
                sxy += x * y
            return (s0 * sxy - s1 * sy) / den

        dh1 = slope("h1")
        dh2 = slope("h2")
        dh3 = slope("h3")
        dh4 = slope("h4")

        f1 = qh(last["h1"], a1)
        f2 = qh(last["h2"], a2)
        f3 = qh(last["h3"], a3)
        f4 = qh(last["h4"], a4)

        # instantaneous flows pumped into the two UPPER tanks
        P_meas = dh4 + f4
        R_meas = dh3 + f3

        r1 = gam1 / (1.0 - gam1)
        r2 = gam2 / (1.0 - gam2)

        # additative feed offsets from the exact lower-tank mass balance
        d1 = dh1 + f1 - f3 - r1 * P_meas
        d2 = dh2 + f2 - f4 - r2 * R_meas
        if d1 > 0.006:
            d1 = 0.006
        if d1 < -0.006:
            d1 = -0.006
        if d2 > 0.006:
            d2 = 0.006
        if d2 < -0.006:
            d2 = -0.006

        # effective upper-tank gains (lump pump loss + split) from balances
        A1e = A1n
        A2e = A2n
        v1m = last["v1"]
        v2m = last["v2"]
        if v1m > 0.5:
            A1e = P_meas / v1m
        if v2m > 0.5:
            A2e = R_meas / v2m
        if A1e > A1n:
            A1e = A1n
        if A2e > A2n:
            A2e = A2n
        if A1e < 0.40 * A1n:
            A1e = 0.40 * A1n
        if A2e < 0.40 * A2n:
            A2e = 0.40 * A2n

        # ---------- margined constraint envelope ----------
        VHI = 11.5
        VLO = 1.5
        HB_LO = h2_lo + 0.02
        HB_HI = h2_hi - 0.02
        if HB_HI < HB_LO:
            midb = 0.5 * (HB_LO + HB_HI)
            HB_LO = midb
            HB_HI = midb
        HUP3 = ulim - 0.03
        HUP4 = ulim - 0.03
        if HUP3 < 0.01:
            HUP3 = ulim
        if HUP4 < 0.01:
            HUP4 = ulim
        W_CON = 3000.0
        W_TR = 350.0

        # ---------- feasible q1 range (safety limits) ----------
        h1min = max(0.02, lo_lim)
        h1max = min(1.5, hi_lim)
        h2min = max(0.02, lo_lim)
        h2max = min(1.5, hi_lim)
        qlo = qh(h1min, a1)
        t = Q - qh(h2max, a2)
        if t > qlo:
            qlo = t
        qhi = qh(h1max, a1)
        t = Q - qh(h2min, a2)
        if t < qhi:
            qhi = t
        if qhi < qlo + 1.0e-9:
            midq = 0.5 * (qlo + qhi)
            qlo = midq
            qhi = midq + 1.0e-9

        # ---------- scan the constant-production curve ----------
        best_q1 = None
        best_c = None
        K = 300
        for k in range(K + 1):
            q1 = qlo + (qhi - qlo) * float(k) / float(K)
            q2 = Q - q1
            if q1 <= 0.0 or q2 <= 0.0:
                continue
            X = q1 - d1
            Y = q2 - d2
            P = (4.0 * Y - X) / 3.75
            R = (4.0 * X - Y) / 3.75
            if P <= 0.0 or R <= 0.0:
                continue
            h1p = hq(q1, a1)
            h2p = hq(q2, a2)
            h3p = (R / (a3 * S2)) ** 2
            h4p = (P / (a4 * S2)) ** 2
            v1p = P / A1e
            v2p = R / A2e
            c = W_TR * (abs(h1p - h1_cur) + abs(h2p - h2_cur))
            if h3p > HUP3:
                c += W_CON * (h3p - HUP3)
            if h4p > HUP4:
                c += W_CON * (h4p - HUP4)
            if h2p < HB_LO:
                c += W_CON * (HB_LO - h2p)
            if h2p > HB_HI:
                c += W_CON * (h2p - HB_HI)
            if v1p > VHI:
                c += W_CON * (v1p - VHI)
            if v2p > VHI:
                c += W_CON * (v2p - VHI)
            if v1p < VLO:
                c += W_CON * (VLO - v1p)
            if v2p < VLO:
                c += W_CON * (VLO - v2p)
            if best_c is None or c < best_c:
                best_c = c
                best_q1 = q1

        if best_q1 is None:
            return {
                "diagnosis": "no feasible split on the target curve; holding setpoints",
                "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur},
            }

        # ---------- rate limit along the constant-Q curve ----------
        q1_cur = qh(h1_cur, a1)
        if q1_cur < qlo:
            q1_cur = qlo
        if q1_cur > qhi:
            q1_cur = qhi
        dq = 0.0008
        q1_new = best_q1
        if q1_new - q1_cur > dq:
            q1_new = q1_cur + dq
        elif q1_cur - q1_new > dq:
            q1_new = q1_cur - dq

        h1_new = hq(q1_new, a1)
        h2_new = hq(Q - q1_new, a2)
        h1_new = min(hi_lim, max(lo_lim, h1_new))
        h2_new = min(hi_lim, max(lo_lim, h2_new))

        if abs(h1_new - h1_cur) < 0.0015 and abs(h2_new - h2_cur) < 0.0015:
            h1_new = h1_cur
            h2_new = h2_cur

        diag = ("mass-balance split: d1=" + str(round(d1 * 1000.0, 2)) +
                " L/s, d2=" + str(round(d2 * 1000.0, 2)) +
                " L/s; minimum-travel point on constant-Q curve inside margined h2/h3/h4/pump envelope")

        return {
            "diagnosis": diag,
            "adjusted_setpoints": {"h1": round(h1_new, 5), "h2": round(h2_new, 5)},
        }
    except Exception:
        return {
            "diagnosis": "fallback after internal error; holding setpoints",
            "adjusted_setpoints": {"h1": h1_fb, "h2": h2_fb},
        }
