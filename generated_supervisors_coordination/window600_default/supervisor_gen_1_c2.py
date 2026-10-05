def supervise(telemetry_window, active_setpoints, objectives):
    A1 = 0.0035
    A2 = 0.003
    A3 = 0.002
    A4 = 0.0025
    G = 19.62
    Aa = 0.00017
    Bb = 0.00019
    C1 = 0.00068
    C2 = 0.00076

    try:
        W = telemetry_window
        n = len(W)
        if n < 1:
            return {"diagnosis": "no data",
                    "adjusted_setpoints": {"h1": float(active_setpoints["h1"]),
                                           "h2": float(active_setpoints["h2"])}}
        Qt = float(objectives["production_target"])
        bl = float(objectives["h2_band"][0])
        bh = float(objectives["h2_band"][1])
        ulim = float(objectives["upper_level_limit"])
        slo = float(objectives["setpoint_limits"][0])
        shi = float(objectives["setpoint_limits"][1])
        sp1 = min(shi, max(slo, float(active_setpoints["h1"])))
        sp2 = min(shi, max(slo, float(active_setpoints["h2"])))

        def sq(x):
            if x <= 0.0:
                return 0.0
            return math.sqrt(x)

        L = 45
        if n - 1 < L:
            L = n - 1
        if L < 1:
            L = 1
        s1 = 0.0
        s2 = 0.0
        for i in range(n - L, n):
            s = W[i]
            s1 += A1 * sq(G * s["h1"]) - A3 * sq(G * s["h3"]) - Aa * s["v1"]
            s2 += A2 * sq(G * s["h2"]) - A4 * sq(G * s["h4"]) - Bb * s["v2"]
        d1 = s1 / L + (W[n - 1]["h1"] - W[n - 1 - L]["h1"]) / L
        d2 = s2 / L + (W[n - 1]["h2"] - W[n - 1 - L]["h2"]) / L
        d1 = min(0.006, max(-0.006, d1))
        d2 = min(0.006, max(-0.006, d2))

        last = W[n - 1]
        v1m = last["v1"]
        v2m = last["v2"]
        k3n = (C2 / A3) ** 2 / G
        k4n = (C1 / A4) ** 2 / G
        k3 = k3n
        if v2m > 1.5:
            k3 = last["h3"] / (v2m * v2m)
            k3 = min(3.0 * k3n, max(0.3 * k3n, k3))
        k4 = k4n
        if v1m > 1.5:
            k4 = last["h4"] / (v1m * v1m)
            k4 = min(3.0 * k4n, max(0.3 * k4n, k4))

        den = C1 - Aa * Bb / C2

        def predict(h1s, h2s):
            Q1 = A1 * sq(G * h1s)
            Q2 = A2 * sq(G * h2s)
            v1u = ((Q2 - d2) - (Bb / C2) * (Q1 - d1)) / den
            v2u = (Q1 - d1 - Aa * v1u) / C2
            v1 = v1u
            v2 = v2u
            Q1a = Q1
            Q2a = Q2
            if v1u > 12.0 or v2u > 12.0:
                if v1u > 12.0 and v2u > 12.0:
                    v1 = 12.0
                    v2 = 12.0
                    Q1a = C2 * v2 + Aa * v1 + d1
                    Q2a = C1 * v1 + Bb * v2 + d2
                elif v1u > 12.0:
                    v1 = 12.0
                    v2 = (Q1 - d1 - Aa * v1) / C2
                    if v2 > 12.0:
                        v2 = 12.0
                        Q1a = C2 * v2 + Aa * v1 + d1
                    Q2a = C1 * v1 + Bb * v2 + d2
                else:
                    v2 = 12.0
                    v1 = (Q2 - d2 - Bb * v2) / C1
                    if v1 > 12.0:
                        v1 = 12.0
                        Q2a = C1 * v1 + Bb * v2 + d2
                    Q1a = C2 * v2 + Aa * v1 + d1
            if v1 < 1.0:
                v1 = 1.0
            if v2 < 1.0:
                v2 = 1.0
            if Q1a < 0.0:
                Q1a = 0.0
            if Q2a < 0.0:
                Q2a = 0.0
            h1a = (Q1a / A1) ** 2 / G
            h2a = (Q2a / A2) ** 2 / G
            h3a = k3 * v2 * v2
            h4a = k4 * v1 * v1
            return Q1a, Q2a, h1a, h2a, h3a, h4a

        def cost(h1s, h2s):
            Q1a, Q2a, h1a, h2a, h3a, h4a = predict(h1s, h2s)
            c = 200.0 * abs(1000.0 * (Q1a + Q2a) - Qt)
            if h2a > bh:
                c += 400.0 + 1500.0 * (h2a - bh)
            elif h2a < bl:
                c += 400.0 + 1500.0 * (bl - h2a)
            sft = ulim - 0.03
            if h3a > ulim:
                c += 400.0 + 2500.0 * (h3a - ulim)
            elif h3a > sft:
                c += 400.0 * (h3a - sft)
            if h4a > ulim:
                c += 400.0 + 2500.0 * (h4a - ulim)
            elif h4a > sft:
                c += 400.0 * (h4a - sft)
            if h1a < 0.02 or h1a > 1.5:
                c += 3000.0
            if h2a < 0.02 or h2a > 1.5:
                c += 3000.0
            c += 100.0 * (abs(h1s - sp1) + abs(h2s - sp2))
            return c

        h1lo = max(slo, 0.05)
        h1hi = min(shi, 0.80)
        h2lo = max(slo, 0.08)
        h2hi = min(shi, 0.80)

        best_h1 = sp1
        best_h2 = sp2
        best_c = cost(sp1, sp2)

        ni = int((h1hi - h1lo) / 0.02) + 1
        nj = int((h2hi - h2lo) / 0.02) + 1
        for i in range(ni + 1):
            h1s = h1lo + 0.02 * i
            if h1s > h1hi:
                h1s = h1hi
            for j in range(nj + 1):
                h2s = h2lo + 0.02 * j
                if h2s > h2hi:
                    h2s = h2hi
                c = cost(h1s, h2s)
                if c < best_c:
                    best_c = c
                    best_h1 = h1s
                    best_h2 = h2s

        ch1 = best_h1
        ch2 = best_h2
        cc = best_c
        for k in range(2):
            b1 = ch1
            b2 = ch2
            n1 = ch1
            n2 = ch2
            nc = cc
            for i in range(-3, 4):
                for j in range(-3, 4):
                    h1s = b1 + 0.006 * i
                    h2s = b2 + 0.006 * j
                    if h1s < h1lo or h1s > h1hi or h2s < h2lo or h2s > h2hi:
                        continue
                    c = cost(h1s, h2s)
                    if c < nc:
                        nc = c
                        n1 = h1s
                        n2 = h2s
            ch1 = n1
            ch2 = n2
            cc = nc

        cur_c = cost(sp1, sp2)
        if cc < cur_c - 25.0 and (abs(ch1 - sp1) + abs(ch2 - sp2)) > 0.012:
            o1 = min(shi, max(slo, round(ch1, 4)))
            o2 = min(shi, max(slo, round(ch2, 4)))
            diag = ("rebalance h1=" + str(round(o1, 3)) + " h2=" + str(round(o2, 3))
                    + " d1=" + str(round(d1 * 1000.0, 2)) + " d2=" + str(round(d2 * 1000.0, 2))
                    + " L/s")
        else:
            o1 = sp1
            o2 = sp2
            diag = ("hold h1=" + str(round(o1, 3)) + " h2=" + str(round(o2, 3))
                    + " d1=" + str(round(d1 * 1000.0, 2)) + " d2=" + str(round(d2 * 1000.0, 2))
                    + " L/s")

        return {"diagnosis": diag,
                "adjusted_setpoints": {"h1": float(o1), "h2": float(o2)}}
    except Exception:
        try:
            a1 = float(active_setpoints["h1"])
            a2 = float(active_setpoints["h2"])
        except Exception:
            a1 = 0.30
            a2 = 0.35
        return {"diagnosis": "fallback hold",
                "adjusted_setpoints": {"h1": a1, "h2": a2}}
