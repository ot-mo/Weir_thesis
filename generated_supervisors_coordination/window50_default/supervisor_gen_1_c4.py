def supervise(telemetry_window, active_setpoints, objectives):
    import math
    g = 9.81
    sqrt2g = math.sqrt(2.0 * g)
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025

    if not telemetry_window:
        return {"diagnosis": "no telemetry", "adjusted_setpoints": active_setpoints}

    s = telemetry_window[-1]
    h1_cur = s["h1"]
    h2_cur = s["h2"]
    h3_cur = s["h3"]
    h4_cur = s["h4"]
    v1_cur = s["v1"]
    v2_cur = s["v2"]

    Q_t = objectives["production_target"]
    h2_low, h2_high = objectives["h2_band"]
    upper_limit = objectives["upper_level_limit"]
    sp_low, sp_high = objectives["setpoint_limits"]

    h1_sp = active_setpoints["h1"]
    h2_sp = active_setpoints["h2"]

    def Q1(h):
        return a1 * math.sqrt(2.0 * g * h) if h > 0.0 else 0.0
    def Q2(h):
        return a2 * math.sqrt(2.0 * g * h) if h > 0.0 else 0.0
    def clamp(x, lo, hi):
        return max(lo, min(hi, x))

    Q_sp = Q1(h1_sp) + Q2(h2_sp)
    if Q_sp > 1e-9 and abs(Q_sp - Q_t) > 0.05:
        f = (Q_t / Q_sp) ** 2
        h1_sp *= f
        h2_sp *= f

    h1_sp = clamp(h1_sp, max(sp_low, 0.02), min(sp_high, 1.5))
    h2_sp = clamp(h2_sp, max(sp_low, 0.02), min(sp_high, 1.5))

    Q1_sp = Q1(h1_sp)

    Q1_low = 0.0
    Q1_high = Q_t

    Q2_min = Q2(h2_low)
    Q2_max = Q2(h2_high)
    Q1_low = max(Q1_low, Q_t - Q2_max)
    Q1_high = min(Q1_high, Q_t - Q2_min)

    Q1_low = max(Q1_low, Q1(0.02))
    Q1_high = min(Q1_high, Q1(1.5))
    Q2_min_safety = Q2(0.02)
    Q2_max_safety = Q2(1.5)
    Q1_low = max(Q1_low, Q_t - Q2_max_safety)
    Q1_high = min(Q1_high, Q_t - Q2_min_safety)

    h3_target = upper_limit - 0.05
    if h3_cur > h3_target and h3_cur > 1e-9 and v2_cur > 1e-9:
        v2_target = v2_cur * math.sqrt(h3_target / h3_cur)
        b_eff = a3 * math.sqrt(2.0 * g * h3_cur) / v2_cur
        Q1_cur = Q1(h1_cur)
        Q1_max_h3 = Q1_cur + b_eff * (v2_target - v2_cur)
        Q1_high = min(Q1_high, Q1_max_h3)

    h4_target = upper_limit - 0.05
    if h4_cur > h4_target and h4_cur > 1e-9 and v1_cur > 1e-9:
        v1_target = v1_cur * math.sqrt(h4_target / h4_cur)
        d_eff = a4 * math.sqrt(2.0 * g * h4_cur) / v1_cur
        Q2_cur = Q2(h2_cur)
        Q2_max_h4 = Q2_cur + d_eff * (v1_target - v1_cur)
        Q1_min_h4 = Q_t - Q2_max_h4
        Q1_low = max(Q1_low, Q1_min_h4)

    v2_max = 11.5
    if v2_cur > v2_max and h3_cur > 1e-9 and v2_cur > 1e-9:
        b_eff = a3 * math.sqrt(2.0 * g * h3_cur) / v2_cur
        Q1_cur = Q1(h1_cur)
        Q1_max_v2 = Q1_cur + b_eff * (v2_max - v2_cur)
        Q1_high = min(Q1_high, Q1_max_v2)

    v1_max = 11.5
    if v1_cur > v1_max and h4_cur > 1e-9 and v1_cur > 1e-9:
        d_eff = a4 * math.sqrt(2.0 * g * h4_cur) / v1_cur
        Q2_cur = Q2(h2_cur)
        Q2_max_v1 = Q2_cur + d_eff * (v1_max - v1_cur)
        Q1_min_v1 = Q_t - Q2_max_v1
        Q1_low = max(Q1_low, Q1_min_v1)

    if Q1_low > Q1_high:
        Q1_target = 0.5 * (Q1_low + Q1_high)
        diag = "constraint conflict: balancing"
    else:
        Q1_target = clamp(Q1_sp, Q1_low, Q1_high)
        diag = "tracking Q and constraints"

    Q2_target = Q_t - Q1_target
    h1_new = (Q1_target / (a1 * sqrt2g)) ** 2 if Q1_target > 0.0 else 0.02
    h2_new = (Q2_target / (a2 * sqrt2g)) ** 2 if Q2_target > 0.0 else 0.02

    h1_new = clamp(h1_new, max(sp_low, 0.02), min(sp_high, 1.5))
    h2_new = clamp(h2_new, max(sp_low, 0.02), min(sp_high, 1.5))

    return {
        "diagnosis": diag + ": h1_sp=%.3f, h2_sp=%.3f" % (h1_new, h2_new),
        "adjusted_setpoints": {"h1": h1_new, "h2": h2_new},
    }
