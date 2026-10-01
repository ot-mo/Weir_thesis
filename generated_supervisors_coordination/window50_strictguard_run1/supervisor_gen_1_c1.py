def supervise(telemetry_window, active_setpoints, objectives):
    try:
        g = 9.81
        r2g = 2.0 * g
        a1 = 0.0035
        a2 = 0.003
        a3 = 0.002
        a4 = 0.0025
        k1n = 0.00085
        k2n = 0.00095

        Q = float(objectives["production_target"]) / 1000.0
        h2_lo = float(objectives["h2_band"][0])
        h2_hi = float(objectives["h2_band"][1])
        ulim = float(objectives["upper_level_limit"])
        sp_lo = float(objectives["setpoint_limits"][0])
        sp_hi = float(objectives["setpoint_limits"][1])

        h1a = float(active_setpoints["h1"])
        h2a = float(active_setpoints["h2"])

        n = len(telemetry_window)
        if n < 1 or Q <= 0.0:
            return {"diagnosis": "no data or no target: hold setpoints",
                    "adjusted_setpoints": {"h1": h1a, "h2": h2a}}

        s1 = 0.0; s2 = 0.0; s3 = 0.0; s4 = 0.0; sv1 = 0.0; sv2 = 0.0
        for s in telemetry_window:
            s1 += s["h1"]
            s2 += s["h2"]
            s3 += s["h3"]
            s4 += s["h4"]
            sv1 += s["v1"]
            sv2 += s["v2"]
        m1 = s1 / n
        m2 = s2 / n
        m3 = s3 / n
        m4 = s4 / n
        mv1 = sv1 / n
        mv2 = sv2 / n

        if mv1 < 0.2:
            mv1 = 0.2
        if mv2 < 0.2:
            mv2 = 0.2

        # effective gains: A = (1-gamma2)*k2 (v2 -> tank3 flow), C = (1-gamma1)*k1
        A = a3 * math.sqrt(r2g * max(m3, 1e-6)) / mv2
        if A < 0.00030:
            A = 0.00030
        if A > 0.00130:
            A = 0.00130
        C = a4 * math.sqrt(r2g * max(m4, 1e-6)) / mv1
        if C < 0.00025:
            C = 0.00025
        if C > 0.00110:
            C = 0.00110

        # assume nominal split gamma = 0.2, so B = gamma1*k1 = 0.25*C, D = 0.25*A
        B = 0.25 * C
        D = 0.25 * A

        q1m = a1 * math.sqrt(r2g * max(m1, 0.0))
        q2m = a2 * math.sqrt(r2g * max(m2, 0.0))
        d1 = q1m - A * mv2 - B * mv1
        d2 = q2m - D * mv2 - C * mv1

        NC = 241
        best_c = None
        bh1 = h1a
        bh2 = h2a
        for i in range(1, NC + 1):
            q1 = Q * i / (NC + 1)
            q2 = Q - q1
            if q1 <= 0.0 or q2 <= 0.0:
                continue
            h1p = (q1 / a1) ** 2 / r2g
            h2p = (q2 / a2) ** 2 / r2g
            r1 = q1 - d1
            r2 = q2 - d2
            v2p = (r1 - 0.25 * r2) / (0.9375 * A)
            v1p = (r2 - 0.25 * r1) / (0.9375 * C)
            if v2p < 0.0:
                v2p = 0.0
            if v1p < 0.0:
                v1p = 0.0
            h3p = (A * v2p / a3) ** 2 / r2g
            h4p = (C * v1p / a4) ** 2 / r2g

            c = 100.0 * (abs(h1p - h1a) + abs(h2p - h2a))
            if h2p < h2_lo:
                c += 300.0 + 3000.0 * (h2_lo - h2p)
            elif h2p > h2_hi:
                c += 300.0 + 3000.0 * (h2p - h2_hi)
            if h3p > ulim:
                c += 500.0 + 3000.0 * (h3p - ulim)
            if h4p > ulim:
                c += 500.0 + 3000.0 * (h4p - ulim)
            c += 100.0 * max(0.0, h3p - (ulim - 0.06))
            c += 100.0 * max(0.0, h4p - (ulim - 0.06))
            if h1p < 0.02 or h1p > 1.5:
                c += 8000.0
            if h2p < 0.02 or h2p > 1.5:
                c += 8000.0
            if v1p > 12.0:
                c += 300.0 * (v1p - 12.0)
            if v2p > 12.0:
                c += 300.0 * (v2p - 12.0)
            if v1p < 1.0:
                c += 300.0 * (1.0 - v1p)
            if v2p < 1.0:
                c += 300.0 * (1.0 - v2p)
            if best_c is None or c < best_c:
                best_c = c
                bh1 = h1p
                bh2 = h2p

        if bh1 < sp_lo:
            bh1 = sp_lo
        if bh1 > sp_hi:
            bh1 = sp_hi
        if bh2 < sp_lo:
            bh2 = sp_lo
        if bh2 > sp_hi:
            bh2 = sp_hi

        last = telemetry_window[-1]
        urgent = (last["h3"] > ulim - 0.04) or (last["h4"] > ulim - 0.04)
        alpha = 0.7 if urgent else 0.25

        dh1 = bh1 - h1a
        dh2 = bh2 - h2a
        if abs(dh1) < 0.004:
            dh1 = 0.0
        if abs(dh2) < 0.004:
            dh2 = 0.0

        nh1 = h1a + alpha * dh1
        nh2 = h2a + alpha * dh2
        if nh1 < sp_lo:
            nh1 = sp_lo
        if nh1 > sp_hi:
            nh1 = sp_hi
        if nh2 < sp_lo:
            nh2 = sp_lo
        if nh2 > sp_hi:
            nh2 = sp_hi

        msg = "Q*=%.2f L/s; h3=%.3f h4=%.3f; A=%.5f C=%.5f; sp=(%.3f,%.3f)" % (
            Q * 1000.0, m3, m4, A, C, nh1, nh2)
        return {"diagnosis": msg,
                "adjusted_setpoints": {"h1": nh1, "h2": nh2}}
    except Exception:
        return {"diagnosis": "exception: hold setpoints",
                "adjusted_setpoints": {"h1": active_setpoints["h1"],
                                       "h2": active_setpoints["h2"]}}