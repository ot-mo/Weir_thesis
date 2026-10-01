def supervise(telemetry_window, active_setpoints, objectives):
    try:
        g = 9.81
        sq = math.sqrt(2.0 * g)
        a1 = 0.0035
        a2 = 0.0030
        a3 = 0.0020
        a4 = 0.0025
        k1n = 0.00085
        k2n = 0.00095
        gam1 = 0.20
        gam2 = 0.20
        c1n = gam1 / (1.0 - gam1)
        c2n = gam2 / (1.0 - gam2)
        p1n = (1.0 - gam1) * k1n
        p2n = (1.0 - gam2) * k2n
        VMIN = 1.0
        VMAX = 12.0

        h1_act = float(active_setpoints["h1"])
        h2_act = float(active_setpoints["h2"])
        target_prod = float(objectives["production_target"])
        qt = target_prod / 1000.0
        h2_lo_b = float(objectives["h2_band"][0])
        h2_hi_b = float(objectives["h2_band"][1])
        ulim = float(objectives["upper_level_limit"])
        sp_lo = float(objectives["setpoint_limits"][0])
        sp_hi = float(objectives["setpoint_limits"][1])

        w = telemetry_window
        n = len(w)
        if n < 5:
            return {"diagnosis": "insufficient telemetry: holding setpoints",
                    "adjusted_setpoints": {"h1": h1_act, "h2": h2_act}}

        W = 20
        if W > n:
            W = n
        start = n - W
        if start < 0:
            start = 0

        sum_u1v1 = 0.0
        sum_v1sq = 0.0
        sum_u2v2 = 0.0
        sum_v2sq = 0.0
        N1 = 0
        sum_x1 = 0.0
        sum_y1 = 0.0
        sum_x1y1 = 0.0
        sum_x1sq = 0.0
        N2 = 0
        sum_x2 = 0.0
        sum_y2 = 0.0
        sum_x2y2 = 0.0
        sum_x2sq = 0.0

        for i in range(start, n - 1):
            dt_i = float(w[i + 1]["time"]) - float(w[i]["time"])
            if dt_i <= 0.0:
                dt_i = 1.0
            h1 = float(w[i]["h1"])
            if h1 < 0.0:
                h1 = 0.0
            h2 = float(w[i]["h2"])
            if h2 < 0.0:
                h2 = 0.0
            h3 = float(w[i]["h3"])
            if h3 < 0.0:
                h3 = 0.0
            h4 = float(w[i]["h4"])
            if h4 < 0.0:
                h4 = 0.0
            h3n = float(w[i + 1]["h3"])
            if h3n < 0.0:
                h3n = 0.0
            h4n = float(w[i + 1]["h4"])
            if h4n < 0.0:
                h4n = 0.0
            v1 = float(w[i]["v1"])
            v2 = float(w[i]["v2"])

            F1 = a1 * sq * math.sqrt(h1)
            F2 = a2 * sq * math.sqrt(h2)
            u2 = (h3n - h3) / dt_i + a3 * sq * math.sqrt(h3)
            u1 = (h4n - h4) / dt_i + a4 * sq * math.sqrt(h4)

            if v1 > 0.5:
                sum_u1v1 += u1 * v1
                sum_v1sq += v1 * v1
            if v2 > 0.5:
                sum_u2v2 += u2 * v2
                sum_v2sq += v2 * v2

            y1 = F1 - u2
            x1 = u1
            sum_x1 += x1
            sum_y1 += y1
            sum_x1y1 += x1 * y1
            sum_x1sq += x1 * x1
            N1 += 1

            y2 = F2 - u1
            x2 = u2
            sum_x2 += x2
            sum_y2 += y2
            sum_x2y2 += x2 * y2
            sum_x2sq += x2 * x2
            N2 += 1

        if sum_v1sq > 1e-12:
            p1_est = sum_u1v1 / sum_v1sq
        else:
            p1_est = p1n
        if sum_v2sq > 1e-12:
            p2_est = sum_u2v2 / sum_v2sq
        else:
            p2_est = p2n
        if p1_est < 0.3 * p1n:
            p1_est = 0.3 * p1n
        if p1_est > 1.5 * p1n:
            p1_est = 1.5 * p1n
        if p2_est < 0.3 * p2n:
            p2_est = 0.3 * p2n
        if p2_est > 1.5 * p2n:
            p2_est = 1.5 * p2n

        if N1 >= 2:
            denom1 = N1 * sum_x1sq - sum_x1 * sum_x1
            if abs(denom1) > 1e-12:
                c1_est = (N1 * sum_x1y1 - sum_x1 * sum_y1) / denom1
                d1_est = (sum_y1 - c1_est * sum_x1) / N1
            else:
                c1_est = c1n
                d1_est = 0.0
        else:
            c1_est = c1n
            d1_est = 0.0
        if c1_est < 0.0:
            c1_est = 0.0
        if c1_est > 1.0:
            c1_est = 1.0
        if d1_est > 0.005:
            d1_est = 0.005
        if d1_est < -0.005:
            d1_est = -0.005

        if N2 >= 2:
            denom2 = N2 * sum_x2sq - sum_x2 * sum_x2
            if abs(denom2) > 1e-12:
                c2_est = (N2 * sum_x2y2 - sum_x2 * sum_y2) / denom2
                d2_est = (sum_y2 - c2_est * sum_x2) / N2
            else:
                c2_est = c2n
                d2_est = 0.0
        else:
            c2_est = c2n
            d2_est = 0.0
        if c2_est < 0.0:
            c2_est = 0.0
        if c2_est > 1.0:
            c2_est = 1.0
        if d2_est > 0.005:
            d2_est = 0.005
        if d2_est < -0.005:
            d2_est = -0.005

        c1 = c1_est
        c2 = c2_est
        d1 = d1_est
        d2 = d2_est
        p1 = p1_est
        p2 = p2_est

        den = 1.0 - c1 * c2
        if den < 0.1:
            den = 0.1

        A1 = (qt - d2 + c2 * d1) / den
        B1 = (1.0 + c2) / den
        C = -d1 - c1 * A1
        D = 1.0 + c1 * B1

        h3_margin = ulim - 0.02
        if h3_margin < 0.05:
            h3_margin = 0.05
        h4_margin = ulim - 0.02
        if h4_margin < 0.05:
            h4_margin = 0.05
        u2_cap = a3 * sq * math.sqrt(h3_margin)
        u2_vol = p2 * VMAX
        u2_max = u2_cap if u2_cap < u2_vol else u2_vol
        u2_min = p2 * VMIN
        u1_cap = a4 * sq * math.sqrt(h4_margin)
        u1_vol = p1 * VMAX
        u1_max = u1_cap if u1_cap < u1_vol else u1_vol
        u1_min = p1 * VMIN

        F1_safe_min = a1 * sq * math.sqrt(0.02)
        F1_safe_max = a1 * sq * math.sqrt(1.45)
        F2_safe_min = a2 * sq * math.sqrt(0.02)
        F2_safe_max = a2 * sq * math.sqrt(1.45)

        h2_lo = h2_lo_b + 0.01
        h2_hi = h2_hi_b - 0.01
        if h2_lo >= h2_hi:
            h2_lo = h2_lo_b
            h2_hi = h2_hi_b
        F2_band_min = a2 * sq * math.sqrt(max(0.0, h2_lo))
        F2_band_max = a2 * sq * math.sqrt(max(0.0, h2_hi))

        hard_lo = F1_safe_min
        hard_hi = F1_safe_max
        v = qt - F2_safe_max
        if v > hard_lo:
            hard_lo = v
        v = qt - F2_safe_min
        if v < hard_hi:
            hard_hi = v
        v = (A1 - u1_max) / B1
        if v > hard_lo:
            hard_lo = v
        v = (A1 - u1_min) / B1
        if v < hard_hi:
            hard_hi = v
        v = (u2_min - C) / D
        if v > hard_lo:
            hard_lo = v
        v = (u2_max - C) / D
        if v < hard_hi:
            hard_hi = v

        band_lo = qt - F2_band_max
        band_hi = qt - F2_band_min

        if hard_lo <= hard_hi and band_lo <= band_hi:
            lo = hard_lo
            hi = hard_hi
            if band_lo > lo:
                lo = band_lo
            if band_hi < hi:
                hi = band_hi
            if lo > hi:
                lo = hard_lo
                hi = hard_hi
        else:
            lo = hard_lo
            hi = hard_hi

        if lo > hi:
            safe_lo = F1_safe_min
            safe_hi = F1_safe_max
            v = qt - F2_safe_max
            if v > safe_lo:
                safe_lo = v
            v = qt - F2_safe_min
            if v < safe_hi:
                safe_hi = v
            if safe_lo <= safe_hi:
                lo = safe_lo
                hi = safe_hi
            else:
                lo = F1_safe_min
                hi = F1_safe_max

        F1c = a1 * sq * math.sqrt(max(0.0, h1_act))
        F2c = a2 * sq * math.sqrt(max(0.0, h2_act))
        tot = F1c + F2c
        if tot > 1e-9:
            sfrac = F1c / tot
        else:
            sfrac = 0.5
        F1_pref = sfrac * qt

        if F1_pref < lo:
            F1_pref = lo
        if F1_pref > hi:
            F1_pref = hi
        F1star = F1_pref
        F2star = qt - F1star
        if F2star < 0.0:
            F2star = 0.0
            F1star = qt
        if F1star < 0.0:
            F1star = 0.0
            F2star = qt

        h1_set = (F1star / (a1 * sq)) ** 2
        h2_set = (F2star / (a2 * sq)) ** 2

        if h1_set < sp_lo:
            h1_set = sp_lo
        if h1_set > sp_hi:
            h1_set = sp_hi
        if h2_set < sp_lo:
            h2_set = sp_lo
        if h2_set > sp_hi:
            h2_set = sp_hi

        diag = ("Q*=" + str(round(target_prod, 2)) +
                " c1=" + str(round(c1, 3)) + " c2=" + str(round(c2, 3)) +
                " d1=" + str(round(d1 * 1000.0, 2)) + " d2=" + str(round(d2 * 1000.0, 2)) +
                " p1=" + str(round(p1 / p1n, 2)) + " p2=" + str(round(p2 / p2n, 2)))
        return {"diagnosis": diag,
                "adjusted_setpoints": {"h1": float(h1_set), "h2": float(h2_set)}}
    except Exception:
        try:
            return {"diagnosis": "fallback: holding setpoints",
                    "adjusted_setpoints": {"h1": float(active_setpoints["h1"]),
                                           "h2": float(active_setpoints["h2"])}}
        except Exception:
            return {"diagnosis": "fallback",
                    "adjusted_setpoints": {"h1": 0.30, "h2": 0.35}}
