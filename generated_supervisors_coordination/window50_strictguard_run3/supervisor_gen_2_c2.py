def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    s = (2.0 * g) ** 0.5
    a1 = 0.0035
    a2 = 0.0030
    a3 = 0.0020
    a4 = 0.0025
    k1n = 0.00085
    k2n = 0.00095
    gam1 = 0.20
    gam2 = 0.20
    NOM = 16.35286638873749

    h1a = 0.30
    h2a = 0.35
    target = NOM
    h2lo = 0.25
    h2hi = 0.45
    uplim = 0.75
    lo_sp = 0.02
    hi_sp = 1.5
    try:
        h1a = float(active_setpoints["h1"])
    except Exception:
        pass
    try:
        h2a = float(active_setpoints["h2"])
    except Exception:
        pass
    try:
        target = float(objectives["production_target"])
    except Exception:
        target = NOM
    try:
        h2lo = float(objectives["h2_band"][0])
        h2hi = float(objectives["h2_band"][1])
    except Exception:
        pass
    try:
        uplim = float(objectives["upper_level_limit"])
    except Exception:
        pass
    try:
        lo_sp = float(objectives["setpoint_limits"][0])
        hi_sp = float(objectives["setpoint_limits"][1])
    except Exception:
        pass

    def clip(v, lo, hi):
        if v < lo:
            return lo
        if v > hi:
            return hi
        return v

    out_h1 = clip(h1a, lo_sp, hi_sp)
    out_h2 = clip(h2a, lo_sp, hi_sp)
    diag = "hold active setpoints"

    try:
        n = len(telemetry_window)
        if n < 1:
            return {"diagnosis": "no telemetry; hold", "adjusted_setpoints": {"h1": out_h1, "h2": out_h2}}
        if target <= 0.0:
            target = NOM

        take = telemetry_window[-10:] if n >= 10 else telemetry_window
        Aacc = 0.0
        Bacc = 0.0
        F3acc = 0.0
        F4acc = 0.0
        v1acc = 0.0
        v2acc = 0.0
        cnt = 0
        for tt in take:
            h1m = float(tt["h1"])
            h2m = float(tt["h2"])
            h3m = float(tt["h3"])
            h4m = float(tt["h4"])
            if h1m < 0.0:
                h1m = 0.0
            if h2m < 0.0:
                h2m = 0.0
            if h3m < 0.0:
                h3m = 0.0
            if h4m < 0.0:
                h4m = 0.0
            Aacc += a1 * s * (h1m ** 0.5)
            Bacc += a2 * s * (h2m ** 0.5)
            F3acc += a3 * s * (h3m ** 0.5)
            F4acc += a4 * s * (h4m ** 0.5)
            v1acc += float(tt["v1"])
            v2acc += float(tt["v2"])
            cnt += 1
        A_m = Aacc / cnt
        B_m = Bacc / cnt
        F3_m = F3acc / cnt
        F4_m = F4acc / cnt
        v1_m = v1acc / cnt
        v2_m = v2acc / cnt

        y1_m = F4_m / (1.0 - gam1)
        y2_m = F3_m / (1.0 - gam2)
        d1 = A_m - F3_m - gam1 * y1_m
        d2 = B_m - F4_m - gam2 * y2_m

        k1eff = k1n
        k2eff = k2n
        if v1_m > 0.5:
            kk = y1_m / v1_m
            if kk > 0.3 * k1n and kk < 3.0 * k1n:
                k1eff = kk
        if v2_m > 0.5:
            kk = y2_m / v2_m
            if kk > 0.3 * k2n and kk < 3.0 * k2n:
                k2eff = kk

        C = target / 1000.0
        det = gam1 * gam2 - (1.0 - gam2) * (1.0 - gam1)

        last = telemetry_window[-1]
        h1l = float(last["h1"])
        h2l = float(last["h2"])
        if h1l < 0.0:
            h1l = 0.0
        if h2l < 0.0:
            h2l = 0.0
        Al = a1 * s * (h1l ** 0.5)
        Bl = a2 * s * (h2l ** 0.5)
        tot = Al + Bl
        if tot > 0.0:
            f_c = Al / tot
        else:
            f_c = 0.5
        FR = 0.06
        f_lo = f_c - FR
        f_hi = f_c + FR
        if f_lo < 0.02:
            f_lo = 0.02
        if f_hi > 0.98:
            f_hi = 0.98

        m3 = uplim - 0.04
        m4 = m3
        if m3 < 0.15:
            m3 = 0.15
            m4 = 0.15

        def eval_f(f):
            Ap = f * C
            Bp = (1.0 - f) * C
            X1 = Ap - d1
            X2 = Bp - d2
            y1 = (X1 * gam2 - (1.0 - gam2) * X2) / det
            y2 = (gam1 * X2 - (1.0 - gam1) * X1) / det
            if y1 < 0.0:
                y1 = 0.0
            if y2 < 0.0:
                y2 = 0.0
            h1p = (Ap / (a1 * s)) ** 2
            h2p = (Bp / (a2 * s)) ** 2
            h3p = ((1.0 - gam2) * y2 / (a3 * s)) ** 2
            h4p = ((1.0 - gam1) * y1 / (a4 * s)) ** 2
            v1p = y1 / k1eff
            v2p = y2 / k2eff
            c = 100.0 * (abs(h1p - h1a) + abs(h2p - h2a))
            c += 2500.0 * max(0.0, h3p - m3)
            c += 2500.0 * max(0.0, h4p - m4)
            c += 2500.0 * max(0.0, h2p - h2hi)
            c += 2500.0 * max(0.0, h2lo - h2p)
            c += 2000.0 * max(0.0, v1p - 11.5)
            c += 2000.0 * max(0.0, v2p - 11.5)
            c += 500.0 * max(0.0, 1.5 - v1p)
            c += 500.0 * max(0.0, 1.5 - v2p)
            c += 3000.0 * max(0.0, 0.06 - h1p)
            c += 3000.0 * max(0.0, h1p - 1.4)
            c += 3000.0 * max(0.0, 0.02 - h2p)
            c += 3000.0 * max(0.0, h2p - 1.4)
            return c, h1p, h2p

        best_c = None
        best_h1 = out_h1
        best_h2 = out_h2
        best_f = f_c
        NST = 96
        for i in range(NST + 1):
            f = f_lo + (f_hi - f_lo) * i / NST
            c, hp1, hp2 = eval_f(f)
            if best_c is None or c < best_c:
                best_c = c
                best_h1 = hp1
                best_h2 = hp2
                best_f = f
        for j in range(-12, 13):
            f = best_f + j * 0.0004
            if f < 0.02 or f > 0.98:
                continue
            c, hp1, hp2 = eval_f(f)
            if c < best_c:
                best_c = c
                best_h1 = hp1
                best_h2 = hp2

        out_h1 = clip(best_h1, lo_sp, hi_sp)
        out_h2 = clip(best_h2, lo_sp, hi_sp)
        diag = "flow-split supervisor; f=" + str(round(best_f, 3)) + "; d1=" + str(round(d1, 6)) + "; d2=" + str(round(d2, 6))
    except Exception:
        out_h1 = clip(h1a, lo_sp, hi_sp)
        out_h2 = clip(h2a, lo_sp, hi_sp)
        diag = "fallback: hold active setpoints"

    return {"diagnosis": diag, "adjusted_setpoints": {"h1": out_h1, "h2": out_h2}}
