def supervise(telemetry_window, active_setpoints, objectives):
    try:
        g = 9.81
        a1 = 0.0035
        a2 = 0.003
        a3 = 0.002
        a4 = 0.0025
        k1n = 0.00085
        k2n = 0.00095
        g1 = 0.2
        g2 = 0.2
        sq2g = math.sqrt(2.0 * g)
        Q_target = float(objectives["production_target"])
        q_t = Q_target / 1000.0
        band_lo = float(objectives["h2_band"][0])
        band_hi = float(objectives["h2_band"][1])
        h3_limit = float(objectives["upper_level_limit"])
        h4_limit = float(objectives["upper_level_limit"])
        sp_lo = float(objectives["setpoint_limits"][0])
        sp_hi = float(objectives["setpoint_limits"][1])

        W = telemetry_window
        n = len(W)
        if n < 2:
            return {"diagnosis": "insufficient data", "adjusted_setpoints": {"h1": float(active_setpoints["h1"]), "h2": float(active_setpoints["h2"])}}

        sp_h1_c = float(active_setpoints["h1"])
        sp_h2_c = float(active_setpoints["h2"])

        M = min(25, n - 1)
        sum_k1 = 0.0
        sum_k2 = 0.0
        sum_d1 = 0.0
        sum_d2 = 0.0
        cnt = 0
        for idx in range(n - M, n):
            cur = W[idx]
            prev = W[idx - 1]
            dt = cur["time"] - prev["time"]
            if dt <= 0:
                dt = 1.0
            h1c = float(cur["h1"])
            h2c = float(cur["h2"])
            h3c = float(cur["h3"])
            h4c = float(cur["h4"])
            v1c = float(cur["v1"])
            v2c = float(cur["v2"])
            dh3 = (h3c - float(prev["h3"])) / dt
            dh4 = (h4c - float(prev["h4"])) / dt
            dh1 = (h1c - float(prev["h1"])) / dt
            dh2 = (h2c - float(prev["h2"])) / dt

            if v2c > 0.5:
                k2e = (a3 * sq2g * math.sqrt(max(h3c, 0.0)) + dh3) / v2c
            else:
                k2e = k2n * (1.0 - g2)
            if v1c > 0.5:
                k1e = (a4 * sq2g * math.sqrt(max(h4c, 0.0)) + dh4) / v1c
            else:
                k1e = k1n * (1.0 - g1)

            kl1 = 0.25 * k1n * (1.0 - g1)
            kh1 = 1.6 * k1n * (1.0 - g1)
            kl2 = 0.25 * k2n * (1.0 - g2)
            kh2 = 1.6 * k2n * (1.0 - g2)
            if k1e < kl1:
                k1e = kl1
            if k1e > kh1:
                k1e = kh1
            if k2e < kl2:
                k2e = kl2
            if k2e > kh2:
                k2e = kh2

            q1 = a1 * sq2g * math.sqrt(max(h1c, 0.0))
            q2 = a2 * sq2g * math.sqrt(max(h2c, 0.0))
            B = 0.25 * k1e
            D = 0.25 * k2e
            d1 = dh1 + q1 - k2e * v2c - B * v1c
            d2 = dh2 + q2 - k1e * v1c - D * v2c
            sum_k1 += k1e
            sum_k2 += k2e
            sum_d1 += d1
            sum_d2 += d2
            cnt += 1

        if cnt > 0:
            k1e = sum_k1 / cnt
            k2e = sum_k2 / cnt
            d1 = sum_d1 / cnt
            d2 = sum_d2 / cnt
        else:
            k1e = k1n * (1.0 - g1)
            k2e = k2n * (1.0 - g2)
            d1 = 0.0
            d2 = 0.0

        def q2_of(h2):
            if h2 <= 0.0:
                return 0.0
            return a2 * sq2g * math.sqrt(h2)

        def h1_of_q1(q1):
            if q1 <= 0.0:
                return 0.0
            return (q1 / (a1 * sq2g)) ** 2

        h2_lo = max(band_lo + 0.005, 0.0)
        h2_hi = min(band_hi - 0.005, 1.5)
        if h2_hi < h2_lo:
            h2_lo, h2_hi = h2_hi, h2_lo
        if h2_hi - h2_lo < 0.001:
            h2_lo = band_lo
            h2_hi = band_hi

        steps = 120
        feasible_best = None
        feasible_cost = 1e18
        fallback_best = None
        fallback_cost = 1e18

        for i in range(steps + 1):
            h2c = h2_lo + (h2_hi - h2_lo) * i / steps
            q2c = q2_of(h2c)
            q1c = q_t - q2c
            if q1c <= 0.00002:
                continue
            h1c = h1_of_q1(q1c)
            if h1c < 0.02 or h1c > 1.5:
                continue
            if h1c < sp_lo or h1c > sp_hi:
                continue
            if h2c < sp_lo or h2c > sp_hi:
                continue

            A = k2e
            C = k1e
            B = 0.25 * k1e
            D = 0.25 * k2e
            det = A * C - B * D
            if det <= 1e-12:
                continue

            v2p = (C * (q1c - d1) - B * (q2c - d2)) / det
            v1p = (A * (q2c - d2) - D * (q1c - d1)) / det

            if v2p <= 0.0:
                h3p = 0.0
            else:
                h3p = (A * v2p / (a3 * sq2g)) ** 2
            if v1p <= 0.0:
                h4p = 0.0
            else:
                h4p = (C * v1p / (a4 * sq2g)) ** 2

            travel = abs(h1c - sp_h1_c) + abs(h2c - sp_h2_c)

            feasible = True
            if v2p < 1.0 or v2p > 11.6:
                feasible = False
            if v1p < 1.0 or v1p > 11.6:
                feasible = False
            if h3p > 0.72:
                feasible = False
            if h4p > 0.72:
                feasible = False

            if feasible:
                if travel < feasible_cost:
                    feasible_cost = travel
                    feasible_best = (h1c, h2c)

            pen = 0.0
            if h3p > 0.72:
                pen += (h3p - 0.72) * 200.0
            if h4p > 0.72:
                pen += (h4p - 0.72) * 200.0
            if v2p > 11.5:
                pen += (v2p - 11.5) * 5.0
            if v1p > 11.5:
                pen += (v1p - 11.5) * 5.0
            if v2p < 1.0:
                pen += (1.0 - v2p) * 5.0
            if v1p < 1.0:
                pen += (1.0 - v1p) * 5.0
            if h2c < band_lo:
                pen += (band_lo - h2c) * 200.0
            if h2c > band_hi:
                pen += (h2c - band_hi) * 200.0
            cost = travel + pen
            if cost < fallback_cost:
                fallback_cost = cost
                fallback_best = (h1c, h2c)

        if feasible_best is not None:
            h1_new, h2_new = feasible_best
        elif fallback_best is not None:
            h1_new, h2_new = fallback_best
        else:
            h2c = band_lo
            q2c = q2_of(h2c)
            q1c = q_t - q2c
            if q1c < 0.00002:
                q1c = 0.00002
            h1c = h1_of_q1(q1c)
            if h1c < 0.02:
                h1c = 0.02
            if h1c > 1.5:
                h1c = 1.5
            h2c = max(band_lo, min(band_hi, h2c))
            h1_new = max(sp_lo, min(sp_hi, h1c))
            h2_new = max(sp_lo, min(sp_hi, h2c))

        h1_new = max(0.02, min(1.5, h1_new))
        h2_new = max(0.02, min(1.5, h2_new))
        h1_new = max(sp_lo, min(sp_hi, h1_new))
        h2_new = max(sp_lo, min(sp_hi, h2_new))
        if abs(h1_new - sp_h1_c) < 0.0015 and abs(h2_new - sp_h2_c) < 0.0015:
            h1_new = sp_h1_c
            h2_new = sp_h2_c

        diag = "Q=%.2f k1e=%.5f k2e=%.5f d1=%.5f d2=%.5f sp=(%.4f,%.4f)" % (Q_target, k1e, k2e, d1, d2, h1_new, h2_new)
        return {"diagnosis": diag, "adjusted_setpoints": {"h1": float(h1_new), "h2": float(h2_new)}}
    except Exception:
        try:
            return {"diagnosis": "exception fallback", "adjusted_setpoints": {"h1": float(active_setpoints["h1"]), "h2": float(active_setpoints["h2"])}}
        except Exception:
            return {"diagnosis": "exception fallback", "adjusted_setpoints": {"h1": 0.3, "h2": 0.35}}