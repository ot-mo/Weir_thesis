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

        sF1 = 0.0
        sF2 = 0.0
        sU3 = 0.0
        sU4 = 0.0
        sV1 = 0.0
        sV2 = 0.0
        for r in w:
            x = float(r["h1"])
            if x < 0.0:
                x = 0.0
            sF1 += a1 * math.sqrt(2.0 * g * x)
            x = float(r["h2"])
            if x < 0.0:
                x = 0.0
            sF2 += a2 * math.sqrt(2.0 * g * x)
            x = float(r["h3"])
            if x < 0.0:
                x = 0.0
            sU3 += a3 * math.sqrt(2.0 * g * x)
            x = float(r["h4"])
            if x < 0.0:
                x = 0.0
            sU4 += a4 * math.sqrt(2.0 * g * x)
            sV1 += float(r["v1"])
            sV2 += float(r["v2"])
        mF1 = sF1 / n
        mF2 = sF2 / n
        mU3 = sU3 / n
        mU4 = sU4 / n
        mV1 = sV1 / n
        mV2 = sV2 / n

        h3_start = float(w[0]["h3"])
        h3_end = float(w[-1]["h3"])
        h4_start = float(w[0]["h4"])
        h4_end = float(w[-1]["h4"])
        h3_slope = (h3_end - h3_start) / dt
        h4_slope = (h4_end - h4_start) / dt

        if mV2 > 0.5:
            p2 = ((h3_end - h3_start) / dt + mU3) / mV2
        else:
            p2 = p2n
        if mV1 > 0.5:
            p1 = ((h4_end - h4_start) / dt + mU4) / mV1
        else:
            p1 = p1n
        if p2 < 0.35 * p2n:
            p2 = 0.35 * p2n
        if p2 > 1.6 * p2n:
            p2 = 1.6 * p2n
        if p1 < 0.35 * p1n:
            p1 = 0.35 * p1n
        if p1 > 1.6 * p1n:
            p1 = 1.6 * p1n

        d1 = (float(w[-1]["h1"]) - float(w[0]["h1"])) / dt + mF1 - mU3 - c1 * p1 * mV1
        d2 = (float(w[-1]["h2"]) - float(w[0]["h2"])) / dt + mF2 - mU4 - c2 * p2 * mV2
        LIM = 0.006
        if d1 > LIM:
            d1 = LIM
        if d1 < -LIM:
            d1 = -LIM
        if d2 > LIM:
            d2 = LIM
        if d2 < -LIM:
            d2 = -LIM

        h3t = ulim - 0.03
        if h3t < 0.05:
            h3t = 0.05
        h4t = ulim - 0.03
        if h4t < 0.05:
            h4t = 0.05
        u3_cap = a3 * sq * math.sqrt(h3t)
        u3_vol = p2 * VMAX
        u3_hi = u3_cap if u3_cap < u3_vol else u3_vol
        u3_lo = p2 * VMIN
        u4_cap = a4 * sq * math.sqrt(h4t)
        u4_vol = p1 * VMAX
        u4_hi = u4_cap if u4_cap < u4_vol else u4_vol
        u4_lo = p1 * VMIN

        h2_hi_t = h2_hi_b - 0.01
        h2_lo_t = h2_lo_b + 0.01
        if h2_hi_t <= h2_lo_t:
            h2_hi_t = h2_hi_b
            h2_lo_t = h2_lo_b

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
        if b < hi:
            hi = b
        b = (u3_lo * den + d1 + c1 * qt - c1 * d2) / (1.0 + c1)
        if b > lo:
            lo = b
        b = (qt - d2 + c2 * d1 - u4_hi * den) / (1.0 + c2)
        if b > lo:
            lo = b
        b = (qt - d2 + c2 * d1 - u4_lo * den) / (1.0 + c2)
        if b < hi:
            hi = b
        b = qt - a2 * sq * math.sqrt(h2_hi_t)
        if b > lo:
            lo = b
        b = qt - a2 * sq * math.sqrt(h2_lo_t)
        if b < hi:
            hi = b
        b = qt - a2 * sq * math.sqrt(h2_hi_b)
        if b > lo:
            lo = b
        b = qt - a2 * sq * math.sqrt(h2_lo_b)
        if b < hi:
            hi = b
        b = qt - a2 * sq * math.sqrt(1.45)
        if b > lo:
            lo = b
        b = qt - a2 * sq * math.sqrt(0.02)
        if b < hi:
            hi = b
        b = a1 * sq * math.sqrt(0.02)
        if b > lo:
            lo = b
        b = a1 * sq * math.sqrt(1.45)
        if b < hi:
            hi = b

        trim3 = 0.0
        soft3 = ulim - 0.07
        if soft3 < 0.1:
            soft3 = 0.1
        if h3_end > soft3:
            excess = h3_end - soft3
            trim3 = 0.001 + 0.005 * excess
            if trim3 > 0.003:
                trim3 = 0.003
            if h3_slope > 0.001:
                trim3 += 0.5 * (h3_slope - 0.001)
            if trim3 > 0.004:
                trim3 = 0.004
        trim4 = 0.0
        soft4 = ulim - 0.07
        if soft4 < 0.1:
            soft4 = 0.1
        if h4_end > soft4:
            excess = h4_end - soft4
            trim4 = 0.001 + 0.005 * excess
            if trim4 > 0.003:
                trim4 = 0.003
            if h4_slope > 0.001:
                trim4 += 0.5 * (h4_slope - 0.001)
            if trim4 > 0.004:
                trim4 = 0.004

        F1_target = F1plan - trim3 + trim4

        if hi < lo:
            F1star = hi
            why = "infeasible: prioritizing upper level"
        else:
            F1star = F1_target
            if F1star < lo:
                F1star = lo
                if trim3 > 0.0001:
                    why = "dynamic trim for h3; limited by h2 band"
                else:
                    why = "split to keep h2 in band"
            elif F1star > hi:
                F1star = hi
                why = "split to keep upper level"
            else:
                why = "split kept; Q on target"

        if F1star < 0.0:
            F1star = 0.0
        F2star = qt - F1star
        if F2star < 0.0:
            F2star = 0.0
            F1star = qt

        h1n = (F1star / (a1 * sq)) ** 2
        h2n = (F2star / (a2 * sq)) ** 2
        if h1n < sp_lo:
            h1n = sp_lo
        if h1n > sp_hi:
            h1n = sp_hi
        if h2n < sp_lo:
            h2n = sp_lo
        if h2n > sp_hi:
            h2n = sp_hi

        max_step = 0.08
        dh1 = h1n - h1_act
        if dh1 > max_step:
            h1n = h1_act + max_step
        if dh1 < -max_step:
            h1n = h1_act - max_step
        dh2 = h2n - h2_act
        if dh2 > max_step:
            h2n = h2_act + max_step
        if dh2 < -max_step:
            h2n = h2_act - max_step

        h1n = round(h1n, 4)
        h2n = round(h2n, 4)

        diag = ("Q*=" + str(round(target_prod, 2)) + " L/s, d1=" +
                str(round(d1 * 1000.0, 2)) + " d2=" + str(round(d2 * 1000.0, 2)) +
                " L/s, p1=" + str(round(p1 / p1n, 2)) + " p2=" +
                str(round(p2 / p2n, 2)) + "x; trim3=" + str(round(trim3*1000, 2)) +
                " trim4=" + str(round(trim4*1000, 2)) + "; " + why)
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
