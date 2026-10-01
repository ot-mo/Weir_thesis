def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    gamma1 = 0.20
    gamma2 = 0.20
    c1 = a1 * math.sqrt(2.0 * g)
    c2 = a2 * math.sqrt(2.0 * g)
    c3 = a3 * math.sqrt(2.0 * g)
    c4 = a4 * math.sqrt(2.0 * g)

    Q_target_L = objectives["production_target"]
    Q = Q_target_L / 1000.0
    if Q <= 1e-9:
        Q = 0.01635

    upper_limit = objectives["upper_level_limit"]
    band = objectives["h2_band"]
    band_low = band[0]
    band_high = band[1]
    set_lo, set_hi = objectives["setpoint_limits"]
    safety_low = 0.02
    safety_high = 1.5

    h1_min = max(safety_low, set_lo)
    h1_max = min(safety_high, set_hi)
    h2_min_eff = max(safety_low, set_lo, band_low + 0.005)
    h2_max_eff = min(safety_high, set_hi, band_high - 0.005)
    if h2_min_eff > h2_max_eff:
        h2_min_eff = max(safety_low, set_lo, band_low)
        h2_max_eff = min(safety_high, set_hi, band_high)
    if h2_min_eff > h2_max_eff:
        h2_min_eff = max(safety_low, set_lo)
        h2_max_eff = min(safety_high, set_hi)

    h1_act = active_setpoints["h1"]
    h2_act = active_setpoints["h2"]
    q1_act = c1 * math.sqrt(max(0.0, h1_act))
    q2_act = c2 * math.sqrt(max(0.0, h2_act))
    sum_act = q1_act + q2_act
    if sum_act > 1e-9:
        f_act = q1_act / sum_act
    else:
        f_act = 0.5

    n = len(telemetry_window)
    if n >= 5:
        last = telemetry_window[-1]
        prev = telemetry_window[-5]
        h1_l = last["h1"]
        h2_l = last["h2"]
        h3_l = last["h3"]
        h4_l = last["h4"]
        v1_l = last["v1"]
        v2_l = last["v2"]
        slope1 = (h1_l - prev["h1"]) / 4.0
        slope2 = (h2_l - prev["h2"]) / 4.0
    else:
        if n == 0:
            return {"diagnosis": "no telemetry", "adjusted_setpoints": {"h1": h1_act, "h2": h2_act}}
        last = telemetry_window[-1]
        h1_l = last["h1"]
        h2_l = last["h2"]
        h3_l = last["h3"]
        h4_l = last["h4"]
        v1_l = last["v1"]
        v2_l = last["v2"]
        slope1 = 0.0
        slope2 = 0.0

    d1 = slope1 + c1 * math.sqrt(max(0.0, h1_l)) - c3 * math.sqrt(max(0.0, h3_l)) - gamma1 * k1 * v1_l
    d2 = slope2 + c2 * math.sqrt(max(0.0, h2_l)) - c4 * math.sqrt(max(0.0, h4_l)) - gamma2 * k2 * v2_l

    f_lo = 0.0
    f_hi = 1.0
    if Q > 1e-9:
        f_lo = max(f_lo, c1 * math.sqrt(h1_min) / Q)
        f_hi = min(f_hi, c1 * math.sqrt(h1_max) / Q)
        f_lo = max(f_lo, 1.0 - c2 * math.sqrt(h2_max_eff) / Q)
        f_hi = min(f_hi, 1.0 - c2 * math.sqrt(h2_min_eff) / Q)
    if f_lo > f_hi:
        f_lo = 0.0
        f_hi = 1.0

    def predict(f):
        q1 = f * Q
        q2 = (1.0 - f) * Q
        h1 = (q1 / c1) ** 2 if q1 > 0 else 0.0
        h2 = (q2 / c2) ** 2 if q2 > 0 else 0.0
        A = gamma1 * k1
        B = (1.0 - gamma2) * k2
        C = (1.0 - gamma1) * k1
        D = gamma2 * k2
        det = A * D - B * C
        if abs(det) < 1e-15:
            return None
        rhs1 = q1 - d1
        rhs2 = q2 - d2
        v1 = (rhs1 * D - rhs2 * B) / det
        v2 = (A * rhs2 - C * rhs1) / det
        h3 = ((B * v2) / a3) ** 2 / (2.0 * g) if v2 > 0 else 0.0
        h4 = ((C * v1) / a4) ** 2 / (2.0 * g) if v1 > 0 else 0.0
        return h1, h2, v1, v2, h3, h4

    trigger = upper_limit - 0.05
    pred_act = predict(f_act) if f_act is not None else None
    need_search = False
    if pred_act is None:
        need_search = True
    else:
        h1_p, h2_p, v1_p, v2_p, h3_p, h4_p = pred_act
        if h3_p > trigger or h4_p > trigger:
            need_search = True
        if v1_p > 11.5 or v2_p > 11.5 or v1_p < 1.5 or v2_p < 1.5:
            need_search = True
        if h2_p < h2_min_eff or h2_p > h2_max_eff:
            need_search = True
        if h1_p < h1_min or h1_p > h1_max:
            need_search = True

    if not need_search:
        q1 = f_act * Q
        q2 = (1.0 - f_act) * Q
        h1 = (q1 / c1) ** 2 if q1 > 0 else 0.0
        h2 = (q2 / c2) ** 2 if q2 > 0 else 0.0
        h1 = min(h1_max, max(h1_min, h1))
        h2 = min(h2_max_eff, max(h2_min_eff, h2))
        return {"diagnosis": "steady: production split retained", "adjusted_setpoints": {"h1": h1, "h2": h2}}

    best_f = f_act
    best_cost = None
    steps = 120
    for i in range(steps + 1):
        f = f_lo + (f_hi - f_lo) * i / steps
        pred = predict(f)
        if pred is None:
            continue
        h1_p, h2_p, v1_p, v2_p, h3_p, h4_p = pred
        cost = 0.0
        if h3_p > upper_limit:
            cost += 100000.0
        if h4_p > upper_limit:
            cost += 100000.0
        if h3_p > trigger:
            cost += 10000.0 * (h3_p - trigger) / max(1e-9, upper_limit - trigger)
        if h4_p > trigger:
            cost += 10000.0 * (h4_p - trigger) / max(1e-9, upper_limit - trigger)
        if v1_p > 12.0 or v1_p < 1.0:
            cost += 100000.0
        if v2_p > 12.0 or v2_p < 1.0:
            cost += 100000.0
        if h2_p < band_low or h2_p > band_high:
            cost += 100000.0
        cost += 100.0 * (abs(h1_p - h1_act) + abs(h2_p - h2_act))
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_f = f

    q1 = best_f * Q
    q2 = (1.0 - best_f) * Q
    h1 = (q1 / c1) ** 2 if q1 > 0 else 0.0
    h2 = (q2 / c2) ** 2 if q2 > 0 else 0.0
    h1 = min(h1_max, max(h1_min, h1))
    h2 = min(h2_max_eff, max(h2_min_eff, h2))
    h2 = min(min(safety_high, set_hi), max(max(safety_low, set_lo), h2))
    diag = "split f=%.3f d1=%.5f d2=%.5f" % (best_f, d1, d2)
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1, "h2": h2}}