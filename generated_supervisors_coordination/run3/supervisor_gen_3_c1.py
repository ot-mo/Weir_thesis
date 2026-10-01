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
        c1 = gam1 / (1.0 - gam1)
        c2 = gam2 / (1.0 - gam2)
        p1n = (1.0 - gam1) * k1n
        p2n = (1.0 - gam2) * k2n
        VMIN = 1.5
        VMAX = 11.5

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
        if n < 2:
            return {"diagnosis": "insufficient telemetry: holding setpoints",
                    "adjusted_setpoints": {"h1": h1_act, "h2": h2_act}}

        M = 30
        if n < M:
            M = n
        start_idx = n - M
        dt_M = float(w[-1]["time"]) - float(w[start_idx]["time"])
        if dt_M < 1.0:
            dt_M = 1.0

        sum_h1 = 0.0
        sum_h2 = 0.0
        sum_h3 = 0.0
        sum_h4 = 0.0
        sum_v1 = 0.0
        sum_v2 = 0.0
        sum_F1 = 0.0
        sum_F2 = 0.0
        sum_U3 = 0.0
        sum_U4 = 0.0
        for i in range(start_idx, n):
            r = w[i]
            h1 = float(r["h1"])
            if h1 < 0.0: h1 = 0.0
            h2 = float(r["h2"])
            if h2 < 0.0: h2 = 0.0
            h3 = float(r["h3"])
            if h3 < 0.0: h3 = 0.0
            h4 = float(r["h4"])
            if h4 < 0.0: h4 = 0.0
            sum_h1 += h1
            sum_h2 += h2
            sum_h3 += h3
            sum_h4 += h4
            sum_v1 += float(r["v1"])
            sum_v2 += float(r["v2"])
            sum_F1 += a1 * sq * math.sqrt(h1)
            sum_F2 += a2 * sq * math.sqrt(h2)
            sum_U3 += a3 * sq * math.sqrt(h3)
            sum_U4 += a4 * sq * math.sqrt(h4)

        avg_h1 = sum_h1 / M
        avg_h2 = sum_h2 / M
        avg_h3 = sum_h3 / M
        avg_h4 = sum_h4 / M
        avg_v1 = sum_v1 / M
        avg_v2 = sum_v2 / M
        avg_F1 = sum_F1 / M
        avg_F2 = sum_F2 / M
        avg_U3 = sum_U3 / M
        avg_U4 = sum_U4 / M

        h1_first = float(w[start_idx]["h1"])
        h2_first = float(w[start_idx]["h2"])
        h3_first = float(w[start_idx]["h3"])
        h4_first = float(w[start_idx]["h4"])
        h1_last = float(w[-1]["h1"])
        h2_last = float(w[-1]["h2"])
        h3_last = float(w[-1]["h3"])
        h4_last = float(w[-1]["h4"])
        slope_h1 = (h1_last - h1_first) / dt_M
        slope_h2 = (h2_last - h2_first) / dt_M
        slope_h3 = (h3_last - h3_first) / dt_M
        slope_h4 = (h4_last - h4_first) / dt_M

        h1c = h1_last
        h2c = h2_last
        h3c = h3_last
        h4c = h4_last

        if avg_v2 > 0.5:
            p2 = (slope_h3 + avg_U3) / avg_v2
        else:
            p2 = p2n
        if avg_v1 > 0.5:
            p1 = (slope_h4 + avg_U4) / avg_v1
        else:
            p1 = p1n
        if p2 < 0.35 * p2n: p2 = 0.35 * p2n
        if p2 > 1.6 * p2n: p2 = 1.6 * p2n
        if p1 < 0.35 * p1n: p1 = 0.35 * p1n
        if p1 > 1.6 * p1n: p1 = 1.6 * p1n

        d1 = slope_h1 + avg_F1 - avg_U3 - c1 * p1 * avg_v1
        d2 = slope_h2 + avg_F2 - avg_U4 - c2 * p2 * avg_v2
        if d1 > 0.01: d1 = 0.01
        if d1 < -0.01: d1 = -0.01
        if d2 > 0.01: d2 = 0.01
        if d2 < -0.01: d2 = -0.01

        ha = h1_act
        if ha < 0.0: ha = 0.0
        hb = h2_act
        if hb < 0.0: hb = 0.0
        F1c = a1 * sq * math.sqrt(ha)
        F2c = a2 * sq * math.sqrt(hb)
        tot = F1c + F2c
        if tot > 1.0e-9:
            sfrac = F1c / tot
        else:
            sfrac = 0.5
        F1plan = sfrac * qt
        F1_prev = F1c

        h3_ref = ulim - 0.10
        h4_ref = ulim - 0.10

        margin3 = 0.04
        if slope_h3 > 0.0:
            margin3 += slope_h3 * 15.0
        if h3c > h3_ref:
            margin3 += (h3c - h3_ref) * 0.5
        if margin3 > 0.20: margin3 = 0.20
        h3t = ulim - margin3
        if h3t < 0.05: h3t = 0.05

        margin4 = 0.04
        if slope_h4 > 0.0:
            margin4 += slope_h4 * 15.0
        if h4c > h4_ref:
            margin4 += (h4c - h4_ref) * 0.5
        if margin4 > 0.20: margin4 = 0.20
        h4t = ulim - margin4
        if h4t < 0.05: h4t = 0.05

        h2_hi_t = h2_hi_b - 0.03
        h2_lo_t = h2_lo_b + 0.03
        if h2_hi_t <= h2_lo_t:
            h2_hi_t = h2_hi_b
            h2_lo_t = h2_lo_b

        den = 1.0 - c1 * c2
        lo = 0.0
        hi = 1.0e9

        u3_cap = a3 * sq * math.sqrt(h3t)
        u3_vol = p2 * VMAX
        u3_hi = u3_cap if u3_cap < u3_vol else u3_vol
        u3_lo = p2 * VMIN

        u4_cap = a4 * sq * math.sqrt(h4t)
        u4_vol = p1 * VMAX
        u4_hi = u4_cap if u4_cap < u4_vol else u4_vol
        u4_lo = p1 * VMIN

        b = (u3_hi * den + d1 + c1 * qt - c1 * d2) / (1.0 + c1)
        if b < hi: hi = b
        b = (u3_lo * den + d1 + c1 * qt - c1 * d2) / (1.0 + c1)
        if b > lo: lo = b
        b = (qt - d2 + c2 * d1 - u4_hi * den) / (1.0 + c2)
        if b > lo: lo = b
        b = (qt - d2 + c2 * d1 - u4_lo * den) / (1.0 + c2)
        if b < hi: hi = b
        b = qt - a2 * sq * math.sqrt(h2_hi_t)
        if b > lo: lo = b
        b = qt - a2 * sq * math.sqrt(h2_lo_t)
        if b < hi: hi = b
        b = a1 * sq * math.sqrt(0.02)
        if b > lo: lo = b
        b = a1 * sq * math.sqrt(1.45)
        if b < hi: hi = b
        b = qt - a2 * sq * math.sqrt(0.02)
        if b < hi: hi = b
        b = qt - a2 * sq * math.sqrt(1.45)
        if b > lo: lo = b

        trim3 = -0.03 * (h3c - h3_ref)
        if slope_h3 > 0.0:
            trim3 -= 0.15 * slope_h3
        trim4 = 0.03 * (h4c - h4_ref)
        if slope_h4 > 0.0:
            trim4 += 0.15 * slope_h4

        F1_cmd = F1plan + trim3 + trim4

        if hi >= lo:
            if F1_cmd < lo: F1_cmd = lo
            if F1_cmd > hi: F1_cmd = hi
        else:
            F1_cmd = hi

        max_dF1 = 0.002
        if F1_cmd > F1_prev + max_dF1:
            F1_cmd = F1_prev + max_dF1
        if F1_cmd < F1_prev - max_dF1:
            F1_cmd = F1_prev - max_dF1

        F2_cmd = qt - F1_cmd
        if F2_cmd < 0.0:
            F2_cmd = 0.0
            F1_cmd = qt
        h1n = (F1_cmd / (a1 * sq)) ** 2
        h2n = (F2_cmd / (a2 * sq)) ** 2

        h2_lo_clamp = h2_lo_b + 0.01
        h2_hi_clamp = h2_hi_b - 0.01
        if h2n < h2_lo_clamp: h2n = h2_lo_clamp
        if h2n > h2_hi_clamp: h2n = h2_hi_clamp

        F2_cmd = a2 * sq * math.sqrt(h2n)
        F1_cmd = qt - F2_cmd
        if F1_cmd < 0.0:
            F1_cmd = 0.0
            F2_cmd = qt
            h2n = (F2_cmd / (a2 * sq)) ** 2
            if h2n > h2_hi_clamp: h2n = h2_hi_clamp
            F2_cmd = a2 * sq * math.sqrt(h2n)
            F1_cmd = qt - F2_cmd
        h1n = (F1_cmd / (a1 * sq)) ** 2

        if h1n < 0.02: h1n = 0.02
        if h1n > 1.45: h1n = 1.45
        if h1n < sp_lo: h1n = sp_lo
        if h1n > sp_hi: h1n = sp_hi
        if h2n < sp_lo: h2n = sp_lo
        if h2n > sp_hi: h2n = sp_hi

        diag = ("Q*=" + str(round(target_prod, 2)) + " d1=" +
                str(round(d1 * 1000.0, 2)) + " d2=" + str(round(d2 * 1000.0, 2)) +
                " p1=" + str(round(p1 / p1n, 2)) + " p2=" +
                str(round(p2 / p2n, 2)) + " h3t=" + str(round(h3t, 2)) +
                " h4t=" + str(round(h4t, 2)))
        return {"diagnosis": diag,
                "adjusted_setpoints": {"h1": float(h1n), "h2": float(h2n)}}
    except Exception:
        try:
            return {"diagnosis": "fallback: holding setpoints",
                    "adjusted_setpoints": {"h1": float(active_setpoints["h1"]),
                                           "h2": float(active_setpoints["h2"])}}
        except Exception:
            return {"diagnosis": "fallback",
                    "adjusted_setpoints": {"h1": 0.30, "h2": 0.35}}
