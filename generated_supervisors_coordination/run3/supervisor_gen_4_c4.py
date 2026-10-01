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
        gam1n = 0.20
        gam2n = 0.20
        c1n = gam1n / (1.0 - gam1n)
        c2n = gam2n / (1.0 - gam2n)
        p1n = (1.0 - gam1n) * k1n
        p2n = (1.0 - gam2n) * k2n
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
        if n < 2:
            return {"diagnosis": "insufficient telemetry: holding setpoints",
                    "adjusted_setpoints": {"h1": h1_act, "h2": h2_act}}
        dt = float(w[-1]["time"]) - float(w[0]["time"])
        if dt < 1.0:
            dt = 1.0

        sF1 = 0.0; sF2 = 0.0; sU3 = 0.0; sU4 = 0.0; sV1 = 0.0; sV2 = 0.0
        list_u3 = []; list_u4 = []; list_F1 = []; list_F2 = []
        for r in w:
            x = float(r["h1"]); x = x if x > 0.0 else 0.0
            f1 = a1 * math.sqrt(2.0 * g * x)
            sF1 += f1; list_F1.append(f1)
            x = float(r["h2"]); x = x if x > 0.0 else 0.0
            f2 = a2 * math.sqrt(2.0 * g * x)
            sF2 += f2; list_F2.append(f2)
            x = float(r["h3"]); x = x if x > 0.0 else 0.0
            u3 = a3 * math.sqrt(2.0 * g * x)
            sU3 += u3; list_u3.append(u3)
            x = float(r["h4"]); x = x if x > 0.0 else 0.0
            u4 = a4 * math.sqrt(2.0 * g * x)
            sU4 += u4; list_u4.append(u4)
            sV1 += float(r["v1"])
            sV2 += float(r["v2"])
        mF1 = sF1 / n
        mF2 = sF2 / n
        mU3 = sU3 / n
        mU4 = sU4 / n
        mV1 = sV1 / n
        mV2 = sV2 / n

        slope_h1 = (float(w[-1]["h1"]) - float(w[0]["h1"])) / dt
        slope_h2 = (float(w[-1]["h2"]) - float(w[0]["h2"])) / dt
        slope_h3 = (float(w[-1]["h3"]) - float(w[0]["h3"])) / dt
        slope_h4 = (float(w[-1]["h4"]) - float(w[0]["h4"])) / dt

        if mV1 > 0.5:
            p1 = (slope_h4 + mU4) / mV1
        else:
            p1 = p1n
        if mV2 > 0.5:
            p2 = (slope_h3 + mU3) / mV2
        else:
            p2 = p2n
        p1 = max(0.35 * p1n, min(1.6 * p1n, p1))
        p2 = max(0.35 * p2n, min(1.6 * p2n, p2))

        sum_u4 = 0.0; sum_y1 = 0.0; sum_u4_y1 = 0.0; sum_u4_sq = 0.0
        for i in range(n):
            u4 = list_u4[i]
            y1 = slope_h1 + list_F1[i] - list_u3[i]
            sum_u4 += u4
            sum_y1 += y1
            sum_u4_y1 += u4 * y1
            sum_u4_sq += u4 * u4
        mean_u4 = sum_u4 / n
        mean_y1 = sum_y1 / n
        var_u4 = sum_u4_sq / n - mean_u4 * mean_u4
        if var_u4 > 1e-9:
            cov_u4_y1 = sum_u4_y1 / n - mean_u4 * mean_y1
            c1 = cov_u4_y1 / var_u4
            d1 = mean_y1 - c1 * mean_u4
        else:
            c1 = c1n
            d1 = mean_y1 - c1 * mean_u4
        c1 = max(0.05, min(1.0, c1))
        d1 = max(-0.01, min(0.01, d1))

        sum_u3 = 0.0; sum_y2 = 0.0; sum_u3_y2 = 0.0; sum_u3_sq = 0.0
        for i in range(n):
            u3 = list_u3[i]
            y2 = slope_h2 + list_F2[i] - list_u4[i]
            sum_u3 += u3
            sum_y2 += y2
            sum_u3_y2 += u3 * y2
            sum_u3_sq += u3 * u3
        mean_u3 = sum_u3 / n
        mean_y2 = sum_y2 / n
        var_u3 = sum_u3_sq / n - mean_u3 * mean_u3
        if var_u3 > 1e-9:
            cov_u3_y2 = sum_u3_y2 / n - mean_u3 * mean_y2
            c2 = cov_u3_y2 / var_u3
            d2 = mean_y2 - c2 * mean_u3
        else:
            c2 = c2n
            d2 = mean_y2 - c2 * mean_u3
        c2 = max(0.05, min(1.0, c2))
        d2 = max(-0.01, min(0.01, d2))

        den = 1.0 - c1 * c2
        if den < 0.1:
            den = 0.1

        h3t = ulim - 0.03
        h4t = ulim - 0.03
        if h3t < 0.05: h3t = 0.05
        if h4t < 0.05: h4t = 0.05
        h2_hi_t = h2_hi_b - 0.01
        h2_lo_t = h2_lo_b + 0.01
        if h2_hi_t <= h2_lo_t:
            h2_hi_t = h2_hi_b
            h2_lo_t = h2_lo_b

        u3_cap = a3 * sq * math.sqrt(h3t)
        u3_vol = p2 * VMAX
        u3_hi = min(u3_cap, u3_vol)
        u3_lo = p2 * VMIN
        u4_cap = a4 * sq * math.sqrt(h4t)
        u4_vol = p1 * VMAX
        u4_hi = min(u4_cap, u4_vol)
        u4_lo = p1 * VMIN

        ha = h1_act if h1_act > 0.0 else 0.0
        hb = h2_act if h2_act > 0.0 else 0.0
        F1c = a1 * sq * math.sqrt(ha)
        F2c = a2 * sq * math.sqrt(hb)
        tot = F1c + F2c
        sfrac = (F1c / tot) if tot > 1.0e-9 else 0.5
        F1plan = sfrac * qt

        lo = 0.0
        hi = 1.0e9
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
        b = qt - a2 * sq * math.sqrt(h2_hi_b)
        if b > lo: lo = b
        b = qt - a2 * sq * math.sqrt(h2_lo_b)
        if b < hi: hi = b
        b = qt - a2 * sq * math.sqrt(1.45)
        if b > lo: lo = b
        b = qt - a2 * sq * math.sqrt(0.02)
        if b < hi: hi = b
        b = a1 * sq * math.sqrt(0.02)
        if b > lo: lo = b
        b = a1 * sq * math.sqrt(1.45)
        if b < hi: hi = b

        h3_last = float(w[-1]["h3"])
        h4_last = float(w[-1]["h4"])
        h3_warn = ulim - 0.05
        h4_warn = ulim - 0.05
        delta_F1 = 0.0
        if h3_last > h3_warn:
            delta_F1 -= 0.005 * (h3_last - h3_warn)
        if h4_last > h4_warn:
            delta_F1 += 0.005 * (h4_last - h4_warn)
        F1_target = F1plan + delta_F1

        if hi < lo:
            F1star = hi
            why = "infeasible: prioritizing upper level limits"
        else:
            if F1_target < lo:
                F1star = lo
                why = "split at h2 band limit"
            elif F1_target > hi:
                F1star = hi
                why = "split at upper level limit"
            else:
                F1star = F1_target
                why = "split adjusted for constraints"

        if F1star < 0.0: F1star = 0.0
        F2star = qt - F1star
        if F2star < 0.0: F2star = 0.0

        h1n = (F1star / (a1 * sq)) ** 2
        h2n = (F2star / (a2 * sq)) ** 2
        h1n = max(sp_lo, min(sp_hi, h1n))
        h2n = max(sp_lo, min(sp_hi, h2n))

        max_delta = 0.02
        h1n = max(h1_act - max_delta, min(h1_act + max_delta, h1n))
        h2n = max(h2_act - max_delta, min(h2_act + max_delta, h2n))

        diag = ("Q*=" + str(round(target_prod, 2)) + " L/s, est d1=" +
                str(round(d1 * 1000.0, 2)) + " d2=" + str(round(d2 * 1000.0, 2)) +
                " L/s, c1=" + str(round(c1, 2)) + " c2=" + str(round(c2, 2)) +
                " p1=" + str(round(p1 / p1n, 2)) + " p2=" +
                str(round(p2 / p2n, 2)) + "x nom; " + why)
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