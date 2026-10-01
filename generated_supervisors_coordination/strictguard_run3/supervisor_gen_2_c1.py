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
    NOM_H1 = 0.30
    NOM_H2 = 0.35
    NOM_Q = 1000.0 * (a1 * math.sqrt(2.0 * g * NOM_H1) + a2 * math.sqrt(2.0 * g * NOM_H2))
    Q_t = float(objectives["production_target"])
    lo_sp, hi_sp = objectives["setpoint_limits"]
    band_lo, band_hi = objectives["h2_band"]
    upper_lim = float(objectives["upper_level_limit"])
    h1_min = 0.05
    h1_max = 1.00
    y_min_sp = band_lo + 0.01
    y_max_sp = band_hi - 0.01
    if y_min_sp < 0.02:
        y_min_sp = band_lo
    if y_max_sp > 1.4:
        y_max_sp = band_hi
    scale = (Q_t / NOM_Q) ** 2
    h1_base = NOM_H1 * scale
    h2_base = NOM_H2 * scale
    h1_base = min(max(h1_base, lo_sp), hi_sp)
    h2_base = min(max(h2_base, lo_sp), hi_sp)
    if not telemetry_window:
        return {"diagnosis": "no telemetry, base recipe", "adjusted_setpoints": {"h1": h1_base, "h2": h2_base}}
    last = telemetry_window[-1]
    h3 = float(last["h3"])
    h4 = float(last["h4"])
    v1 = float(last["v1"])
    v2 = float(last["v2"])
    D = 0.0
    margin = 0.05
    h3_target = upper_lim - margin
    h4_target = upper_lim - margin
    if h3 > h3_target and v2 > 0.5:
        v2_target = v2 * math.sqrt(h3_target / h3)
        dv2 = v2 - v2_target
        if dv2 > 0.0:
            D += dv2 / 20.0
    if h4 > h4_target and v1 > 0.5:
        v1_target = v1 * math.sqrt(h4_target / h4)
        dv1 = v1 - v1_target
        if dv1 > 0.0:
            D -= dv1 / 20.0
    if v2 > 11.0:
        D += (v2 - 11.0) / 20.0
    if v1 > 11.0:
        D -= (v1 - 11.0) / 20.0
    if h3 > upper_lim:
        D += (h3 - upper_lim) * 2.0
    if h4 > upper_lim:
        D -= (h4 - upper_lim) * 2.0
    def x_for_Q_and_y(Q, y):
        qy = 1000.0 * a2 * math.sqrt(2.0 * g * y)
        R = Q - qy
        if R <= 0.0:
            return 0.0
        val = R / (1000.0 * a1)
        return (val * val) / (2.0 * g)
    def y_for_Q(Q, x):
        qx = 1000.0 * a1 * math.sqrt(2.0 * g * x)
        R = Q - qx
        if R <= 0.0:
            return 0.0
        val = R / (1000.0 * a2)
        return (val * val) / (2.0 * g)
    x_at_ymax = x_for_Q_and_y(Q_t, y_max_sp)
    x_at_ymin = x_for_Q_and_y(Q_t, y_min_sp)
    x_low = max(lo_sp, h1_min, x_at_ymax)
    x_high = min(hi_sp, h1_max, x_at_ymin)
    if x_low > x_high:
        x_low = x_high = min(max(h1_base, lo_sp), hi_sp)
    x_des = h1_base - D
    x_des = min(max(x_des, x_low), x_high)
    h1_prev = float(active_setpoints["h1"])
    max_step = 0.12
    x_new = h1_prev + max(-max_step, min(max_step, x_des - h1_prev))
    x_new = min(max(x_new, x_low), x_high)
    x_new = min(max(x_new, lo_sp), hi_sp)
    y_new = y_for_Q(Q_t, x_new)
    y_new = min(max(y_new, y_min_sp), y_max_sp)
    y_new = min(max(y_new, lo_sp), hi_sp)
    if D > 0.005:
        diag = "shift production to h2 to relieve h3/pump2"
    elif D < -0.005:
        diag = "shift production to h1 to relieve h4/pump1"
    elif abs(x_new - h1_prev) > 0.001:
        diag = "target tracking"
    else:
        diag = "base"
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": x_new, "h2": y_new}}