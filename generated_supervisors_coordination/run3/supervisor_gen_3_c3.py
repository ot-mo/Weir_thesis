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
        den = 1.0 - c1 * c2
        VMIN = 1.0
        VMAX = 12.0

        h1_act = float(active_setpoints["h1"])
        h2_act = float(active_setpoints["h2"])
        Q_target = float(objectives["production_target"]) / 1000.0
        h2_lo_b = float(objectives["h2_band"][0])
        h2_hi_b = float(objectives["h2_band"][1])
        ulim = float(objectives["upper_level_limit"])
        sp_lo = float(objectives["setpoint_limits"][0])
        sp_hi = float(objectives["setpoint_limits"][1])

        w = telemetry_window
        n = len(w)
        if n < 2:
            return {"diagnosis": "insufficient telemetry", "adjusted_setpoints": {"h1": h1_act, "h2": h2_act}}

        n_f = float(n)
        t_sum = 0.0
        t2_sum = 0.0
        sum_h1 = 0.0
        sum_h2 = 0.0
        sum_h3 = 0.0
        sum_h4 = 0.0
        sum_v1 = 0.0
        sum_v2 = 0.0
        sum_prod = 0.0
        for r in w:
            t = float(r["time"])
            t_sum += t
            t2_sum += t * t
            sum_h1 += float(r["h1"])
            sum_h2 += float(r["h2"])
            sum_h3 += float(r["h3"])
            sum_h4 += float(r["h4"])
            sum_v1 += float(r["v1"])
            sum_v2 += float(r["v2"])
            sum_prod += float(r["production"])

        t_mean = t_sum / n_f
        denom_t = n_f * t2_sum - t_sum * t_sum
        if abs(denom_t) < 1.0e-9:
            denom_t = 1.0

        def slope(key):
            sum_ty = 0.0
            sum_y = 0.0
            for r in w:
                t = float(r["time"])
                y = float(r[key])
                sum_ty += t * y
                sum_y += y
            return (n_f * sum_ty - t_sum * sum_y) / denom_t

        avg_h1 = sum_h1 / n_f
        avg_h2 = sum_h2 / n_f
        avg_h3 = sum_h3 / n_f
        avg_h4 = sum_h4 / n_f
        avg_v1 = sum_v1 / n_f
        avg_v2 = sum_v2 / n_f
        avg_prod = sum_prod / n_f

        mean_out1 = 0.0
        mean_out2 = 0.0
        mean_out3 = 0.0
        mean_out4 = 0.0
        for r in w:
            x = float(r["h1"])
            if x < 0.0:
                x = 0.0
            mean_out1 += a1 * sq * math.sqrt(x)
            x = float(r["h2"])
            if x < 0.0:
                x = 0.0
            mean_out2 += a2 * sq * math.sqrt(x)
            x = float(r["h3"])
            if x < 0.0:
                x = 0.0
            mean_out3 += a3 * sq * math.sqrt(x)
            x = float(r["h4"])
            if x < 0.0:
                x = 0.0
            mean_out4 += a4 * sq * math.sqrt(x)
        mean_out1 /= n_f
        mean_out2 /= n_f
        mean_out3 /= n_f
        mean_out4 /= n_f

        dh1 = slope("h1")
        dh2 = slope("h2")
        dh3 = slope("h3")
        dh4 = slope("h4")

        if avg_v2 > 0.5:
            p2_est = (dh3 + mean_out3) / avg_v2
        else:
            p2_est = p2n
        if avg_v1 > 0.5:
            p1_est = (dh4 + mean_out4) / avg_v1
        else:
            p1_est = p1n

        p2 = max(0.5 * p2n, min(1.5 * p2n, p2_est))
        p1 = max(0.5 * p1n, min(1.5 * p1n, p1_est))

        d1_est = dh1 + mean_out1 - mean_out3 - c1 * p1 * avg_v1
        d2_est = dh2 + mean_out2 - mean_out4 - c2 * p2 * avg_v2
        LIM = 0.008
        d1 = max(-LIM, min(LIM, d1_est))
        d2 = max(-LIM, min(LIM, d2_est))

        Q_avg_m = avg_prod / 1000.0
        Kq = 0.5
        Q_eff = Q_target + Kq * (Q_target - Q_avg_m)
        Q_eff = max(0.9 * Q_target, min(1.1 * Q_target, Q_eff))

        h3_warn = ulim - 0.05
        h4_warn = ulim - 0.05
        h3_safe = h3_warn - 0.02
        h4_safe = h4_warn - 0.02
        if h3_safe < 0.05:
            h3_safe = 0.05
        if h4_safe < 0.05:
            h4_safe = 0.05
        h3_lim = ulim - 0.03
        h4_lim = ulim - 0.03
        if h3_lim < 0.05:
            h3_lim = 0.05
        if h4_lim < 0.05:
            h4_lim = 0.05

        u3_cap = a3 * sq * math.sqrt(h3_lim)
        u3_vol = p2 * VMAX
        u3_hi = u3_cap if u3_cap < u3_vol else u3_vol
        u3_lo = p2 * VMIN
        u4_cap = a4 * sq * math.sqrt(h4_lim)
        u4_vol = p1 * VMAX
        u4_hi = u4_cap if u4_cap < u4_vol else u4_vol
        u4_lo = p1 * VMIN

        def F1_from_u2(u2):
            return (u2 * den + d1 + c1 * Q_eff - c1 * d2) / (1.0 + c1)

        def F1_from_u1(u1):
            return (Q_eff - d2 + c2 * d1 - u1 * den) / (1.0 + c2)

        lo = 0.0
        hi = Q_eff
        lo = max(lo, F1_from_u2(u3_lo))
        hi = min(hi, F1_from_u2(u3_hi))
        lo = max(lo, F1_from_u1(u4_hi))
        hi = min(hi, F1_from_u1(u4_lo))

        F2_lo_band = a2 * sq * math.sqrt(h2_lo_b)
        F2_hi_band = a2 * sq * math.sqrt(h2_hi_b)
        lo = max(lo, Q_eff - F2_hi_band)
        hi = min(hi, Q_eff - F2_lo_band)
        F1_lo_safe = a1 * sq * math.sqrt(0.02)
        F1_hi_safe = a1 * sq * math.sqrt(1.45)
        lo = max(lo, F1_lo_safe)
        hi = min(hi, F1_hi_safe)

        if lo > hi:
            mid = 0.5 * (lo + hi)
            lo = mid
            hi = mid

        ha = h1_act if h1_act > 0.0 else 0.0
        hb = h2_act if h2_act > 0.0 else 0.0
        F1c = a1 * sq * math.sqrt(ha)
        F2c = a2 * sq * math.sqrt(hb)
        tot = F1c + F2c
        if tot > 1.0e-9:
            sfrac = F1c / tot
        else:
            sfrac = 0.5
        F1_plan = sfrac * Q_eff

        F1_target = F1_plan

        if avg_h3 > h3_warn:
            u2_safe = a3 * sq * math.sqrt(h3_safe)
            F1_max_h3 = F1_from_u2(u2_safe)
            if F1_target > F1_max_h3:
                F1_target = F1_max_h3
        if avg_h4 > h4_warn:
            u1_safe = a4 * sq * math.sqrt(h4_safe)
            F1_min_h4 = F1_from_u1(u1_safe)
            if F1_target < F1_min_h4:
                F1_target = F1_min_h4

        if avg_v2 > 11.5:
            u2_sat = p2 * 11.5
            F1_max_sat = F1_from_u2(u2_sat)
            if F1_target > F1_max_sat:
                F1_target = F1_max_sat
        if avg_v1 > 11.5:
            u1_sat = p1 * 11.5
            F1_min_sat = F1_from_u1(u1_sat)
            if F1_target < F1_min_sat:
                F1_target = F1_min_sat

        if F1_target < lo:
            F1_target = lo
        if F1_target > hi:
            F1_target = hi

        F2_target = Q_eff - F1_target
        if F2_target < 0.0:
            F2_target = 0.0

        h1n = (F1_target / (a1 * sq)) ** 2
        h2n = (F2_target / (a2 * sq)) ** 2

        if h1n < sp_lo:
            h1n = sp_lo
        if h1n > sp_hi:
            h1n = sp_hi
        if h2n < sp_lo:
            h2n = sp_lo
        if h2n > sp_hi:
            h2n = sp_hi
        if h1n < 0.02:
            h1n = 0.02
        if h1n > 1.45:
            h1n = 1.45
        if h2n < 0.02:
            h2n = 0.02
        if h2n > 1.45:
            h2n = 1.45

        if abs(h1n - h1_act) < 0.0015 and abs(h2n - h2_act) < 0.0015:
            h1n = h1_act
            h2n = h2_act

        diag = ("Q*=" + str(round(Q_target * 1000.0, 2)) + " L/s, Q_eff=" +
                str(round(Q_eff * 1000.0, 2)) + ", d1=" + str(round(d1 * 1000.0, 2)) +
                " d2=" + str(round(d2 * 1000.0, 2)) + " L/s, p1=" +
                str(round(p1 / p1n, 2)) + " p2=" + str(round(p2 / p2n, 2)) +
                "x nom; h3=" + str(round(avg_h3, 3)) + " h4=" + str(round(avg_h4, 3)))
        return {"diagnosis": diag, "adjusted_setpoints": {"h1": float(h1n), "h2": float(h2n)}}
    except Exception:
        try:
            return {"diagnosis": "fallback", "adjusted_setpoints": {"h1": float(active_setpoints["h1"]), "h2": float(active_setpoints["h2"])}}
        except Exception:
            return {"diagnosis": "fallback", "adjusted_setpoints": {"h1": 0.30, "h2": 0.35}}
