def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1, a2, a3, a4 = 0.0035, 0.003, 0.002, 0.0025
    k1n, k2n = 0.00085, 0.00095
    gam1, gam2 = 0.20, 0.20
    B = 1.0 - gam2
    C = 1.0 - gam1
    det = gam1 * gam2 - B * C

    h1_cur = float(active_setpoints["h1"])
    h2_cur = float(active_setpoints["h2"])
    fallback = {"diagnosis": "hold (data error)", "adjusted_setpoints": {"h1": h1_cur, "h2": h2_cur}}

    try:
        w = telemetry_window
        n = len(w)
        if n < 3:
            return fallback
        last = w[n - 1]
        h1 = float(last["h1"])
        h2 = float(last["h2"])
        h3 = float(last["h3"])
        h4 = float(last["h4"])
        v1 = float(last["v1"])
        v2 = float(last["v2"])

        j = n - 1 - 10
        if j < 0:
            j = 0
        dt = float(last["time"]) - float(w[j]["time"])
        if dt <= 0.0:
            dt = 1.0
        dh1 = (h1 - float(w[j]["h1"])) / dt
        dh2 = (h2 - float(w[j]["h2"])) / dt
        dh3 = (h3 - float(w[j]["h3"])) / dt
        dh4 = (h4 - float(w[j]["h4"])) / dt

        q1 = a1 * math.sqrt(2.0 * g * max(0.0, h1))
        q2 = a2 * math.sqrt(2.0 * g * max(0.0, h2))
        q3 = a3 * math.sqrt(2.0 * g * max(0.0, h3))
        q4 = a4 * math.sqrt(2.0 * g * max(0.0, h4))

        if v2 > 2.0:
            k2e = (q3 + dh3) / (B * v2)
            if k2e < 0.6 * k2n:
                k2e = 0.6 * k2n
            if k2e > 1.1 * k2n:
                k2e = 1.1 * k2n
        else:
            k2e = k2n
        if v1 > 2.0:
            k1e = (q4 + dh4) / (C * v1)
            if k1e < 0.6 * k1n:
                k1e = 0.6 * k1n
            if k1e > 1.1 * k1n:
                k1e = 1.1 * k1n
        else:
            k1e = k1n

        d1 = dh1 + q1 - q3 - gam1 * k1e * v1
        d2 = dh2 + q2 - q4 - gam2 * k2e * v2
        if d1 < -0.006:
            d1 = -0.006
        if d1 > 0.006:
            d1 = 0.006
        if d2 < -0.006:
            d2 = -0.006
        if d2 > 0.006:
            d2 = 0.006

        Qt = float(objectives["production_target"]) / 1000.0
        band_lo = float(objectives["h2_band"][0])
        band_hi = float(objectives["h2_band"][1])
        uplim = float(objectives["upper_level_limit"])
        sp_lo = float(objectives["setpoint_limits"][0])
        sp_hi = float(objectives["setpoint_limits"][1])

        h3_safe = uplim - 0.04
        h4_safe = uplim - 0.04
        v_safe = 11.5

        best = None
        best_travel = None
        best_soft = None
        best_soft_cost = None

        step = 0.0025
        for i in range(0, 501):
            h2c = 0.03 + i * step
            q2c = a2 * math.sqrt(2.0 * g * h2c)
            q1c = Qt - q2c
            if q1c <= 0.0:
                continue
            t1 = q1c / a1
            h1c = t1 * t1 / (2.0 * g)
            if h1c > 1.6:
                continue
            r1 = q1c - d1
            r2 = q2c - d2
            x1 = (gam2 * r1 - B * r2) / det
            x2 = (gam1 * r2 - C * r1) / det
            if x1 <= 0.0 or x2 <= 0.0:
                continue
            v1c = x1 / k1e
            v2c = x2 / k2e
            t3 = B * x2 / a3
            h3c = t3 * t3 / (2.0 * g)
            t4 = C * x1 / a4
            h4c = t4 * t4 / (2.0 * g)
            travel = abs(h1c - h1_cur) + abs(h2c - h2_cur)

            if (h1c >= sp_lo and h1c <= sp_hi and h2c >= sp_lo and h2c <= sp_hi
                    and h2c >= band_lo and h2c <= band_hi
                    and h3c <= h3_safe and h4c <= h4_safe
                    and v1c <= v_safe and v2c <= v_safe
                    and v1c >= 1.0 and v2c >= 1.0):
                if best_travel is None or travel < best_travel:
                    best_travel = travel
                    best = (h1c, h2c)

            cost = 100.0 * travel
            cost += 100000.0 * (max(0.0, h1c - sp_hi) + max(0.0, sp_lo - h1c))
            cost += 100000.0 * (max(0.0, h2c - sp_hi) + max(0.0, sp_lo - h2c))
            cost += 4000.0 * max(0.0, h3c - uplim)
            cost += 4000.0 * max(0.0, h4c - uplim)
            cost += 4000.0 * max(0.0, band_lo - h2c)
            cost += 4000.0 * max(0.0, h2c - band_hi)
            cost += 3000.0 * max(0.0, v1c - 12.0) + 3000.0 * max(0.0, v2c - 12.0)
            cost += 3000.0 * max(0.0, 1.0 - v1c) + 3000.0 * max(0.0, 1.0 - v2c)
            if best_soft_cost is None or cost < best_soft_cost:
                best_soft_cost = cost
                best_soft = (h1c, h2c)

        if best is not None:
            h1_new, h2_new = best
            if best_travel < 0.0025:
                h1_new, h2_new = h1_cur, h2_cur
            diag = "min-travel feasible split (d1=%.3f L/s, d2=%.3f L/s)" % (d1 * 1000.0, d2 * 1000.0)
        elif best_soft is not None:
            h1_new, h2_new = best_soft
            diag = "no feasible split; least-violation choice (d1=%.3f L/s, d2=%.3f L/s)" % (d1 * 1000.0, d2 * 1000.0)
        else:
            h1_new, h2_new = h1_cur, h2_cur
            diag = "no candidate; hold"

        if h1_new < sp_lo:
            h1_new = sp_lo
        if h1_new > sp_hi:
            h1_new = sp_hi
        if h2_new < sp_lo:
            h2_new = sp_lo
        if h2_new > sp_hi:
            h2_new = sp_hi

        return {"diagnosis": diag, "adjusted_setpoints": {"h1": float(h1_new), "h2": float(h2_new)}}
    except Exception:
        return fallback
