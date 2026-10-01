def supervise(telemetry_window, active_setpoints, objectives):
    try:
        A1, A2, A3, A4 = 0.0035, 0.003, 0.002, 0.0025
        K1, K2 = 0.00085, 0.00095
        G = 9.81
        R = math.sqrt(2.0 * G)
        low_frac = 0.20      # gamma1 = gamma2 = 0.20 -> lower tank
        up_frac = 0.80       # -> upper tank
        DEN = 0.60           # determinant factor (up_frac^2 - low_frac^2)

        def clampf(x, lo, hi):
            if x < lo:
                return lo
            if x > hi:
                return hi
            return x

        Q_target = float(objectives["production_target"])
        band = objectives["h2_band"]
        b_lo = float(band[0]) + 0.005
        b_hi = float(band[1]) - 0.005
        up_lim = float(objectives["upper_level_limit"])
        spl = objectives["setpoint_limits"]
        sp_lo = float(spl[0])
        sp_hi = float(spl[1])
        h1_act = float(active_setpoints["h1"])
        h2_act = float(active_setpoints["h2"])
    except Exception:
        return {"diagnosis": "argument error; holding nominal",
                "adjusted_setpoints": {"h1": 0.30, "h2": 0.35}}

    Qm = Q_target / 1000.0

    try:
        win = telemetry_window
        n = len(win)
        if n < 3:
            return {"diagnosis": "no telemetry; nominal setpoints",
                    "adjusted_setpoints": {"h1": clampf(0.30, sp_lo, sp_hi),
                                           "h2": clampf(0.35, sp_lo, sp_hi)}}
        N = 20
        if n < N:
            N = n
        seg = win[n - N:n]
        h1s = [float(x["h1"]) for x in seg]
        h2s = [float(x["h2"]) for x in seg]
        h3s = [float(x["h3"]) for x in seg]
        h4s = [float(x["h4"]) for x in seg]
        v1s = [float(x["v1"]) for x in seg]
        v2s = [float(x["v2"]) for x in seg]

        def mean(xs):
            t = 0.0
            for x in xs:
                t += x
            return t / len(xs)

        def slope(xs):
            m = len(xs)
            if m < 2:
                return 0.0
            mx = (m - 1) / 2.0
            my = mean(xs)
            sxx = 0.0
            sxy = 0.0
            i = 0
            for x in xs:
                d = i - mx
                sxx += d * d
                sxy += d * (x - my)
                i += 1
            if sxx == 0.0:
                return 0.0
            return sxy / sxx

        h1m = mean(h1s)
        h2m = mean(h2s)
        h3m = mean(h3s)
        h4m = mean(h4s)
        v1m = mean(v1s)
        v2m = mean(v2s)
        dh1 = slope(h1s)
        dh2 = slope(h2s)

        def qf(h, a):
            if h <= 0.0:
                return 0.0
            return a * math.sqrt(2.0 * G * h)

        # effective feed disturbances from exact tank-1/2 balances + slope
        d1 = dh1 + qf(h1m, A1) - qf(h3m, A3) - low_frac * K1 * v1m
        d2 = dh2 + qf(h2m, A2) - qf(h4m, A4) - low_frac * K2 * v2m

        # pump-voltage limits implied by the upper-tank level limit (10% margin)
        v2_lim = A3 * math.sqrt(2.0 * G * 0.90 * up_lim) / (up_frac * K2)
        if v2_lim > 12.0:
            v2_lim = 12.0
        v1_lim = A4 * math.sqrt(2.0 * G * 0.90 * up_lim) / (up_frac * K1)
        if v1_lim > 12.0:
            v1_lim = 12.0

        # search the single production-split degree of freedom
        best_cost = None
        b_h1 = h1_act
        b_h2 = h2_act
        b_f = 0.0
        b_v1 = 0.0
        b_v2 = 0.0
        steps = 130
        fmin = 0.18
        fmax = 0.86
        for i in range(steps + 1):
            f = fmin + (fmax - fmin) * i / float(steps)
            Q1 = f * Qm
            Q2 = Qm - Q1
            if Q1 <= 1e-7 or Q2 <= 1e-7:
                continue
            h1c = (Q1 / (A1 * R)) ** 2
            h2c = (Q2 / (A2 * R)) ** 2
            r1 = Q1 - d1
            r2 = Q2 - d2
            v2p = (up_frac * r1 - low_frac * r2) / (DEN * K2)
            v1p = (up_frac * r2 - low_frac * r1) / (DEN * K1)
            cost = 100.0 * (abs(h1c - h1_act) + abs(h2c - h2_act))
            if v2p > v2_lim:
                cost += 150.0 * (v2p - v2_lim)
            if v1p > v1_lim:
                cost += 150.0 * (v1p - v1_lim)
            if h2c < b_lo:
                cost += 150.0 * (b_lo - h2c)
            elif h2c > b_hi:
                cost += 150.0 * (h2c - b_hi)
            if h1c < 0.021 or h1c > 1.45:
                cost += 1000000.0
            if h2c < 0.021 or h2c > 1.45:
                cost += 1000000.0
            if best_cost is None or cost < best_cost:
                best_cost = cost
                b_h1 = h1c
                b_h2 = h2c
                b_f = f
                b_v1 = v1p
                b_v2 = v2p

        if best_cost is None:
            return {"diagnosis": "no feasible split; holding",
                    "adjusted_setpoints": {"h1": clampf(h1_act, sp_lo, sp_hi),
                                           "h2": clampf(h2_act, sp_lo, sp_hi)}}

        h1_new = clampf(b_h1, sp_lo, sp_hi)
        h2_new = clampf(b_h2, sp_lo, sp_hi)
        diag = ("split f=%.3f; est d1=%.2f d2=%.2f L/s; v_pred=[%.2f,%.2f] "
                "lim=[%.2f,%.2f]" % (b_f, d1 * 1000.0, d2 * 1000.0,
                                     b_v1, b_v2, v1_lim, v2_lim))
        return {"diagnosis": diag,
                "adjusted_setpoints": {"h1": h1_new, "h2": h2_new}}
    except Exception:
        try:
            return {"diagnosis": "fallback; hold active setpoints",
                    "adjusted_setpoints": {"h1": float(active_setpoints["h1"]),
                                           "h2": float(active_setpoints["h2"])}}
        except Exception:
            return {"diagnosis": "fallback",
                    "adjusted_setpoints": {"h1": 0.30, "h2": 0.35}}
