def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    G1 = 0.20
    G2 = 0.20
    s2g = pow(2.0 * g, 0.5)
    K1 = a1 * s2g
    K2 = a2 * s2g

    try:
        target = float(objectives["production_target"])
        qtot = target / 1000.0
        lims = objectives["setpoint_limits"]
        sp_lo = float(lims[0])
        sp_hi = float(lims[1])
        band = objectives["h2_band"]
        band_lo = float(band[0])
        band_hi = float(band[1])
        uplim = float(objectives["upper_level_limit"])

        h1sp0 = float(active_setpoints["h1"])
        h2sp0 = float(active_setpoints["h2"])

        T = telemetry_window
        n = len(T)
        last = T[n - 1]
        first = T[0]
        h1 = float(last["h1"])
        h2 = float(last["h2"])
        h3 = float(last["h3"])
        h4 = float(last["h4"])
        v1 = float(last["v1"])
        v2 = float(last["v2"])

        dt = float(last["time"]) - float(first["time"])
        if dt <= 0.0:
            dt = 1.0
        dh1 = (h1 - float(first["h1"])) / dt
        dh2 = (h2 - float(first["h2"])) / dt

        q1m = K1 * pow(max(h1, 0.0), 0.5)
        q2m = K2 * pow(max(h2, 0.0), 0.5)
        r3 = a3 * pow(max(h3, 0.0) * 2.0 * g, 0.5)
        r4 = a4 * pow(max(h4, 0.0) * 2.0 * g, 0.5)

        # full mass balance gives the external disturbance (uses level slope)
        d1 = dh1 + q1m - r3 - G1 * k1 * v1
        d2 = dh2 + q2m - r4 - G2 * k2 * v2
        dcap = 0.006
        if d1 > dcap: d1 = dcap
        elif d1 < -dcap: d1 = -dcap
        if d2 > dcap: d2 = dcap
        elif d2 < -dcap: d2 = -dcap

        det = k1 * k2 * (G1 * G2 - (1.0 - G1) * (1.0 - G2))
        # v2 = A2*q1 + B2
        A2 = -k1 / det
        B2 = (k1 / det) * (G1 * qtot + (1.0 - G1) * d1 - G1 * d2)
        # v1 = A1*q1 + B1
        A1 = k2 / det
        B1 = (k2 / det) * (-(1.0 - G2) * qtot - G2 * d1 + (1.0 - G2) * d2)

        c2n = (1.0 - G2) * k2 / a3
        c4n = (1.0 - G1) * k1 / a4
        if v2 > 0.3:
            c2m = pow(max(h3, 0.0) * 2.0 * g, 0.5) / v2
        else:
            c2m = c2n
        if v1 > 0.3:
            c4m = pow(max(h4, 0.0) * 2.0 * g, 0.5) / v1
        else:
            c4m = c4n
        c2 = max(c2n, c2m)
        c4 = max(c4n, c4m)

        h3des = uplim - 0.05
        if h3des < 0.25: h3des = 0.25
        h4des = uplim - 0.05
        if h4des < 0.25: h4des = 0.25
        v2safe = pow(2.0 * g * h3des, 0.5) / c2
        v1safe = pow(2.0 * g * h4des, 0.5) / c4

        q1sp = K1 * pow(max(h1sp0, 0.0), 0.5)
        q2sp = K2 * pow(max(h2sp0, 0.0), 0.5)
        qsp = q1sp + q2sp
        if qsp > 1e-9:
            q1pref = q1sp * (qtot / qsp)
        else:
            q1pref = 0.52 * qtot

        lbs = []
        ubs = []
        # keep h2 inside its band
        lbs.append(qtot - K2 * pow(band_hi, 0.5))
        ubs.append(qtot - K2 * pow(band_lo, 0.5))
        # h1 safety limits
        lbs.append(K1 * pow(0.02, 0.5))
        ubs.append(K1 * pow(1.5, 0.5))
        # keep h3 under the limit (via pump2 voltage)
        ubs.append((v2safe - B2) / A2)
        # keep h4 under the limit (via pump1 voltage)
        lbs.append((v1safe - B1) / A1)
        # pump limits 1..12 V
        ubs.append((12.0 - B2) / A2)
        lbs.append((1.0 - B2) / A2)
        lbs.append((12.0 - B1) / A1)
        ubs.append((1.0 - B1) / A1)

        lo_q = max(lbs)
        hi_q = min(ubs)
        if lo_q <= hi_q:
            q1 = min(hi_q, max(lo_q, q1pref))
            note = "feasible"
        else:
            q1 = 0.5 * (lo_q + hi_q)
            note = "infeasible"
        if q1 < 1e-6:
            q1 = 1e-6
        q2 = qtot - q1
        if q2 < 1e-6:
            q2 = 1e-6
            q1 = qtot - q2
            if q1 < 1e-6:
                q1 = 0.5 * qtot
                q2 = 0.5 * qtot

        nh1 = pow(q1 / K1, 2.0)
        nh2 = pow(q2 / K2, 2.0)

        nh1 = min(1.5, max(0.02, nh1))
        nh2 = min(1.5, max(0.02, nh2))
        nh1 = min(sp_hi, max(sp_lo, nh1))
        nh2 = min(sp_hi, max(sp_lo, nh2))

        if abs(nh1 - h1sp0) < 0.002 and abs(nh2 - h2sp0) < 0.002:
            nh1 = min(sp_hi, max(sp_lo, h1sp0))
            nh2 = min(sp_hi, max(sp_lo, h2sp0))

        v2p = A2 * q1 + B2
        v1p = A1 * q1 + B1
        diag = "split q1=%.5f q2=%.5f d1=%.5f d2=%.5f v1p=%.2f v2p=%.2f %s" % (
            q1, q2, d1, d2, v1p, v2p, note)
        return {
            "diagnosis": diag[:180],
            "adjusted_setpoints": {"h1": nh1, "h2": nh2},
        }
    except Exception:
        try:
            lims = objectives["setpoint_limits"]
            sp_lo = float(lims[0])
            sp_hi = float(lims[1])
            h1 = min(sp_hi, max(sp_lo, float(active_setpoints["h1"])))
            h2 = min(sp_hi, max(sp_lo, float(active_setpoints["h2"])))
        except Exception:
            h1 = 0.3
            h2 = 0.35
        return {
            "diagnosis": "fallback: hold previous setpoints",
            "adjusted_setpoints": {"h1": h1, "h2": h2},
        }
