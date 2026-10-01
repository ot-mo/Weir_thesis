def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1, a2, a3, a4 = 0.0035, 0.003, 0.002, 0.0025
    K1 = 1000.0 * a1
    K2 = 1000.0 * a2
    K3 = 1000.0 * a3
    K4 = 1000.0 * a4

    Qtar = float(objectives["production_target"])
    slo, shi = objectives["setpoint_limits"]
    bl, bh = objectives["h2_band"]
    ulim = float(objectives["upper_level_limit"])

    h1c = float(active_setpoints["h1"])
    h2c = float(active_setpoints["h2"])

    w = telemetry_window
    L = len(w)
    if L < 3:
        return {"diagnosis": "insufficient telemetry; holding setpoints",
                "adjusted_setpoints": {"h1": h1c, "h2": h2c}}

    def flow(h, K):
        if h <= 0.0:
            return 0.0
        return K * math.sqrt(2.0 * g * h)

    def clamp(x, lo, hi):
        if x < lo:
            return lo
        if x > hi:
            return hi
        return x

    last = w[-1]
    h1m = float(last["h1"])
    h2m = float(last["h2"])
    h3m = float(last["h3"])
    h4m = float(last["h4"])
    v1m = float(last["v1"])
    v2m = float(last["v2"])

    c1m = flow(h1m, K1)
    c2m = flow(h2m, K2)
    c3m = flow(h3m, K3)
    c4m = flow(h4m, K4)

    k = L - 1
    if k > 8:
        k = 8
    kf = float(k)
    dh1 = (float(w[-1]["h1"]) - float(w[-1 - k]["h1"])) / kf
    dh2 = (float(w[-1]["h2"]) - float(w[-1 - k]["h2"])) / kf
    dh3 = (float(w[-1]["h3"]) - float(w[-1 - k]["h3"])) / kf
    dh4 = (float(w[-1]["h4"]) - float(w[-1 - k]["h4"])) / kf

    # effective upper-tank feed gains (L/s per volt)
    if v2m > 0.5:
        beta2 = (1000.0 * dh3 + c3m) / v2m
    else:
        beta2 = 0.76
    if v1m > 0.5:
        beta1 = (1000.0 * dh4 + c4m) / v1m
    else:
        beta1 = 0.68
    beta2 = clamp(beta2, 0.25, 1.15)
    beta1 = clamp(beta1, 0.25, 1.10)

    # split fractions assumed at their nominal 0.2
    alpha1 = 0.25 * beta1
    alpha2 = 0.25 * beta2

    det = alpha1 * alpha2 - beta1 * beta2
    if det > -1e-6:
        det = -1e-6

    # on-line feed disturbance estimate (L/s), exact instantaneous mass balance
    d1 = 1000.0 * dh1 + c1m - c3m - alpha1 * v1m
    d2 = 1000.0 * dh2 + c2m - c4m - alpha2 * v2m
    d1 = clamp(d1, -6.0, 6.0)
    d2 = clamp(d2, -6.0, 6.0)

    def predict(cc1, cc2):
        r1 = cc1 - d1
        r2 = cc2 - d2
        v1 = (r1 * alpha2 - beta2 * r2) / det
        v2 = (alpha1 * r2 - beta1 * r1) / det
        v1e = clamp(v1, 1.0, 12.0)
        v2e = clamp(v2, 1.0, 12.0)
        c1a = alpha1 * v1e + beta2 * v2e + d1
        c2a = beta1 * v1e + alpha2 * v2e + d2
        h1p = (max(c1a, 0.0) / K1) ** 2 / (2.0 * g)
        h2p = (max(c2a, 0.0) / K2) ** 2 / (2.0 * g)
        h3p = ((beta2 * v2e) / K3) ** 2 / (2.0 * g)
        h4p = ((beta1 * v1e) / K4) ** 2 / (2.0 * g)
        return v1, v2, h1p, h2p, h3p, h4p, c1a + c2a

    band_lo = bl + 0.005
    band_hi = bh - 0.005
    soft_up = ulim - 0.05

    span = Qtar - 0.4
    if span < 0.2:
        span = 0.2
    N = 320

    best_cost = None
    best_h1 = h1c
    best_h2 = h2c
    best_info = (0.0, 0.0, 0.0, 0.0)

    for i in range(N + 1):
        c1 = 0.2 + span * i / N
        c2 = Qtar - c1
        if c2 <= 0.02:
            continue
        h1s = (c1 / K1) ** 2 / (2.0 * g)
        h2s = (c2 / K2) ** 2 / (2.0 * g)
        h1s = clamp(h1s, slo, shi)
        h2s = clamp(h2s, slo, shi)
        cc1 = flow(h1s, K1)
        cc2 = flow(h2s, K2)
        v1, v2, h1p, h2p, h3p, h4p, Qach = predict(cc1, cc2)

        cost = 100.0 * (abs(h1s - h1c) + abs(h2s - h2c))
        cost += 10.0 * abs(Qach - Qtar)
        if h2p > band_hi:
            cost += 250.0 * (h2p - band_hi)
        if h2p < band_lo:
            cost += 250.0 * (band_lo - h2p)
        if h3p > soft_up:
            cost += 250.0 * (h3p - soft_up)
        if h4p > soft_up:
            cost += 250.0 * (h4p - soft_up)
        if v1 > 11.0:
            cost += 25.0 * (v1 - 11.0)
        if v2 > 11.0:
            cost += 25.0 * (v2 - 11.0)
        if h1p < 0.03:
            cost += 500.0 * (0.03 - h1p)
        if h2p < 0.03:
            cost += 500.0 * (0.03 - h2p)
        if h1p > 1.4:
            cost += 500.0 * (h1p - 1.4)
        if h2p > 1.4:
            cost += 500.0 * (h2p - 1.4)

        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_h1 = h1s
            best_h2 = h2s
            best_info = (v1, v2, h3p, h4p)

    if abs(best_h1 - h1c) < 0.004:
        best_h1 = h1c
    if abs(best_h2 - h2c) < 0.004:
        best_h2 = h2c
    best_h1 = round(clamp(best_h1, slo, shi), 4)
    best_h2 = round(clamp(best_h2, slo, shi), 4)

    diag = ("obs d1=%.2f d2=%.2f b1=%.3f b2=%.3f vpred=(%.1f,%.1f) "
            "h3/h4=(%.2f,%.2f) -> sp=(%.3f,%.3f)" % (
                d1, d2, beta1, beta2, best_info[0], best_info[1],
                best_info[2], best_info[3], best_h1, best_h2))

    return {"diagnosis": diag,
            "adjusted_setpoints": {"h1": best_h1, "h2": best_h2}}
