def supervise(telemetry_window, active_setpoints, objectives):
    try:
        sqrt2g = 4.4294469
        a1 = 0.0035
        a2 = 0.003
        a3 = 0.002
        a4 = 0.0025
        B1_nom = 0.00076
        B2_nom = 0.00068

        N = min(5, len(telemetry_window))
        if N == 0:
            return {"diagnosis": "no data", "adjusted_setpoints": active_setpoints}
        recent = telemetry_window[-N:]
        h1m = sum(s['h1'] for s in recent) / N
        h2m = sum(s['h2'] for s in recent) / N
        h3m = sum(s['h3'] for s in recent) / N
        h4m = sum(s['h4'] for s in recent) / N
        v1m = sum(s['v1'] for s in recent) / N
        v2m = sum(s['v2'] for s in recent) / N

        Q1m = a1 * sqrt2g * (h1m ** 0.5) if h1m > 0 else 0.0
        Q2m = a2 * sqrt2g * (h2m ** 0.5) if h2m > 0 else 0.0

        if v2m > 0.5 and h3m > 0.01:
            B1 = a3 * sqrt2g * (h3m ** 0.5) / v2m
        else:
            B1 = B1_nom
        if v1m > 0.5 and h4m > 0.01:
            B2 = a4 * sqrt2g * (h4m ** 0.5) / v1m
        else:
            B2 = B2_nom
        B1 = max(0.0002, min(0.002, B1))
        B2 = max(0.0002, min(0.002, B2))
        A1 = 0.25 * B2
        A2 = 0.25 * B1
        d1 = Q1m - A1 * v1m - B1 * v2m
        d2 = Q2m - A2 * v2m - B2 * v1m
        k1_eff = A1 + B2
        k2_eff = A2 + B1
        D_total = d1 + d2

        Qtarget = objectives["production_target"] / 1000.0
        u_lim = objectives["upper_level_limit"]
        u_target = u_lim * 0.95
        band_low, band_high = objectives["h2_band"]
        sp_lo, sp_hi = objectives["setpoint_limits"]
        safety_lo, safety_hi = 0.02, 1.5

        V2max = 12.0
        if h3m > 0.01:
            V2max = v2m * (u_target / h3m) ** 0.5
        V2max = min(12.0, max(1.0, V2max))
        V1max = 12.0
        if h4m > 0.01:
            V1max = v1m * (u_target / h4m) ** 0.5
        V1max = min(12.0, max(1.0, V1max))

        Q2_min = a2 * sqrt2g * (band_low ** 0.5) if band_low > 0 else 0.0
        Q2_max = a2 * sqrt2g * (band_high ** 0.5) if band_high > 0 else 0.0

        prod_err = abs(Q1m + Q2m - Qtarget)
        if (h3m <= u_target and h4m <= u_target and
                band_low <= h2m <= band_high and prod_err < 0.0003):
            return {
                "diagnosis": "steady: constraints and production satisfied",
                "adjusted_setpoints": active_setpoints
            }

        v2 = V2max
        if k1_eff > 1e-9:
            v1_req = (Qtarget - D_total - k2_eff * v2) / k1_eff
        else:
            v1_req = 1.0
        if B2 > 1e-9:
            v1_low = max(1.0, (Q2_min - A2 * v2 - d2) / B2)
            v1_high = min(V1max, (Q2_max - A2 * v2 - d2) / B2)
        else:
            v1_low = 1.0
            v1_high = V1max
        v1_low = max(1.0, v1_low)
        v1_high = min(V1max, v1_high)
        if v1_low > v1_high:
            v1 = v1_high
        else:
            if v1_req > v1_high:
                v1 = v1_high
            elif v1_req < v1_low:
                v1 = v1_low
            else:
                v1 = v1_req
        v1 = min(V1max, max(1.0, v1))
        v2 = min(V2max, max(1.0, v2))

        Q1 = A1 * v1 + B1 * v2 + d1
        Q2 = A2 * v2 + B2 * v1 + d2
        if Q1 < 0:
            Q1 = 0.0
        if Q2 < 0:
            Q2 = 0.0

        s1 = (Q1 / (a1 * sqrt2g)) ** 2 if Q1 > 0 else safety_lo
        s2 = (Q2 / (a2 * sqrt2g)) ** 2 if Q2 > 0 else band_low

        s1 = min(sp_hi, max(sp_lo, s1))
        s1 = min(safety_hi, max(safety_lo, s1))
        s2 = min(sp_hi, max(sp_lo, s2))
        s2 = min(safety_hi, max(safety_lo, s2))
        s2 = min(band_high, max(band_low, s2))

        if abs(s1 - active_setpoints["h1"]) < 0.002:
            s1 = active_setpoints["h1"]
        if abs(s2 - active_setpoints["h2"]) < 0.002:
            s2 = active_setpoints["h2"]

        diagnosis = "model-based: v1=%.2f v2=%.2f -> sp=%.3f,%.3f" % (v1, v2, s1, s2)
        return {
            "diagnosis": diagnosis,
            "adjusted_setpoints": {"h1": float(s1), "h2": float(s2)}
        }
    except Exception:
        try:
            NOMINAL_H1 = 0.30
            NOMINAL_H2 = 0.35
            NOMINAL_PRODUCTION = 16.35286638873749
            scale = (objectives["production_target"] / NOMINAL_PRODUCTION) ** 2
            lo, hi = objectives["setpoint_limits"]
            h1 = min(hi, max(lo, NOMINAL_H1 * scale))
            h2 = min(hi, max(lo, NOMINAL_H2 * scale))
            return {
                "diagnosis": "fallback nominal scaled",
                "adjusted_setpoints": {"h1": h1, "h2": h2}
            }
        except Exception:
            return {
                "diagnosis": "fallback active",
                "adjusted_setpoints": active_setpoints
            }