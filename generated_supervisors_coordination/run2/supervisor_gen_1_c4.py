def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    gamma1 = 0.2
    gamma2 = 0.2
    target_Ls = objectives["production_target"]
    Q_t = target_Ls / 1000.0
    h2_min_band, h2_max_band = objectives["h2_band"]
    upper_limit = objectives["upper_level_limit"]
    sp_lo, sp_hi = objectives["setpoint_limits"]
    h1_min_safe = 0.02
    h1_max_safe = 1.5
    h2_min_safe = 0.02
    h2_max_safe = 1.5
    if len(telemetry_window) == 0:
        return {"diagnosis": "no telemetry", "adjusted_setpoints": {"h1": active_setpoints["h1"], "h2": active_setpoints["h2"]}}
    last = telemetry_window[-1]
    h1 = last["h1"]; h2 = last["h2"]; h3 = last["h3"]; h4 = last["h4"]
    v1 = last["v1"]; v2 = last["v2"]
    if len(telemetry_window) >= 5:
        dt = 4.0
        dh1_dt = (telemetry_window[-1]["h1"] - telemetry_window[-5]["h1"]) / dt
        dh2_dt = (telemetry_window[-1]["h2"] - telemetry_window[-5]["h2"]) / dt
    else:
        dh1_dt = 0.0
        dh2_dt = 0.0
    d1_est = dh1_dt + a1 * math.sqrt(2 * g * h1) - a3 * math.sqrt(2 * g * h3) - gamma1 * k1 * v1
    d2_est = dh2_dt + a2 * math.sqrt(2 * g * h2) - a4 * math.sqrt(2 * g * h4) - gamma2 * k2 * v2
    h1sp = active_setpoints["h1"]
    h2sp = active_setpoints["h2"]
    F1_sp = a1 * math.sqrt(2 * g * h1sp) if h1sp > 0 else 0.0
    F2_sp = a2 * math.sqrt(2 * g * h2sp) if h2sp > 0 else 0.0
    total_sp = F1_sp + F2_sp
    x_cur = F1_sp / total_sp if total_sp > 0 else 0.5
    if Q_t > 0:
        F2_min_band = a2 * math.sqrt(2 * g * h2_min_band)
        F2_max_band = a2 * math.sqrt(2 * g * h2_max_band)
        x_min_h2 = 1.0 - F2_max_band / Q_t
        x_max_h2 = 1.0 - F2_min_band / Q_t
    else:
        x_min_h2 = 0.0
        x_max_h2 = 1.0
    if Q_t > 0:
        F1_min_safe = a1 * math.sqrt(2 * g * h1_min_safe)
        F1_max_safe = a1 * math.sqrt(2 * g * h1_max_safe)
        x_min_h1 = F1_min_safe / Q_t
        x_max_h1 = F1_max_safe / Q_t
    else:
        x_min_h1 = 0.0
        x_max_h1 = 1.0
    x_min_base = max(0.0, x_min_h2, x_min_h1)
    x_max_base = min(1.0, x_max_h2, x_max_h1)
    if upper_limit > 0:
        v2_lim = (a3 / ((1 - gamma2) * k2)) * math.sqrt(2 * g * upper_limit)
        v1_lim = (a4 / ((1 - gamma1) * k1)) * math.sqrt(2 * g * upper_limit)
    else:
        v2_lim = 12.0
        v1_lim = 12.0
    v2_max = min(11.5, v2_lim - 0.3)
    if v2_max < 1.0:
        v2_max = 1.0
    v1_max = min(11.5, v1_lim - 0.3)
    if v1_max < 1.0:
        v1_max = 1.0
    C2 = -(1 - gamma1) * d1_est - gamma1 * Q_t + gamma1 * d2_est
    C1 = (1 - gamma2) * Q_t - (1 - gamma2) * d2_est + gamma2 * d1_est
    if Q_t > 0:
        x_max_v2 = (v2_max * (0.60 * k2) - C2) / Q_t
        x_min_v1 = (C1 - v1_max * (0.60 * k1)) / Q_t
    else:
        x_max_v2 = 1.0
        x_min_v1 = 0.0
    x_min = max(x_min_base, x_min_v1)
    x_max = min(x_max_base, x_max_v2)
    if x_min > x_max:
        x_target = x_max_v2
        x_target = max(x_min_h1, min(x_max_h1, x_target))
    else:
        if x_cur < x_min:
            x_target = x_min
        elif x_cur > x_max:
            x_target = x_max
        else:
            x_target = x_cur
    x_target = max(0.0, min(1.0, x_target))
    F1_new = x_target * Q_t
    F2_new = (1 - x_target) * Q_t
    h1_new = (F1_new / a1) ** 2 / (2 * g) if a1 > 0 else 0.0
    h2_new = (F2_new / a2) ** 2 / (2 * g) if a2 > 0 else 0.0
    h1_new = min(sp_hi, max(sp_lo, h1_new))
    h2_new = min(sp_hi, max(sp_lo, h2_new))
    h1_new = min(h1_max_safe, max(h1_min_safe, h1_new))
    h2_new = min(h2_max_safe, max(h2_min_safe, h2_new))
    if abs(h1_new - h1sp) < 0.002 and abs(h2_new - h2sp) < 0.002:
        h1_new = h1sp
        h2_new = h2sp
    diagnosis = f"target={target_Ls:.2f}L/s, x={x_target:.3f}, d1={d1_est*1000:.2f}L/s, d2={d2_est*1000:.2f}L/s, v2_max={v2_max:.2f}"
    return {
        "diagnosis": diagnosis,
        "adjusted_setpoints": {"h1": h1_new, "h2": h2_new}
    }