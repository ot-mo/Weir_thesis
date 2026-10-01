def supervise(telemetry_window, active_setpoints, objectives):
    C1 = 15.502
    C2 = 13.288
    k1_nom = 0.85
    k2_nom = 0.95
    A_nom = 0.17
    B_nom = 0.76
    C_nom = 0.19
    D_nom = 0.68
    Delta_nom = B_nom * D_nom - A_nom * C_nom
    K3_nom = 0.0858
    K4_nom = 0.0614
    
    if not telemetry_window:
        return {"diagnosis": "no telemetry", "adjusted_setpoints": active_setpoints}
    last = telemetry_window[-1]
    h1 = float(last.get("h1", 0.3))
    h2 = float(last.get("h2", 0.35))
    h3 = float(last.get("h3", 0.617))
    h4 = float(last.get("h4", 0.306))
    v1 = float(last.get("v1", 9.0))
    v2 = float(last.get("v2", 9.16))
    
    h1_act = float(active_setpoints.get("h1", 0.3))
    h2_act = float(active_setpoints.get("h2", 0.35))
    
    Q_target = float(objectives.get("production_target", 16.35))
    band = objectives.get("h2_band", [0.25, 0.45])
    band_lo = float(band[0])
    band_hi = float(band[1])
    upper_limit = float(objectives.get("upper_level_limit", 0.75))
    sp_limits = objectives.get("setpoint_limits", [0.02, 1.5])
    sp_lo = float(sp_limits[0])
    sp_hi = float(sp_limits[1])
    
    n = len(telemetry_window)
    idx_start = max(0, n - 10)
    h3_start = float(telemetry_window[idx_start].get("h3", h3))
    h4_start = float(telemetry_window[idx_start].get("h4", h4))
    dt = float(n - 1 - idx_start)
    if dt < 1:
        dt = 1.0
    slope_h3 = (h3 - h3_start) / dt
    slope_h4 = (h4 - h4_start) / dt
    
    if v2 > 1.0 and h3 > 0.01:
        K3_est = math.sqrt(h3) / v2
    else:
        K3_est = K3_nom
    if v1 > 1.0 and h4 > 0.01:
        K4_est = math.sqrt(h4) / v1
    else:
        K4_est = K4_nom
    
    if slope_h3 > 0.0002:
        K3_use = K3_nom
        B_use = B_nom
        C_use = C_nom
    else:
        K3_use = K3_est
        B_use = K3_est * 8.858
        if B_use > k2_nom - 0.01:
            B_use = k2_nom - 0.01
        if B_use < 0.05:
            B_use = 0.05
        C_use = k2_nom - B_use
    
    if slope_h4 > 0.0002:
        K4_use = K4_nom
        D_use = D_nom
        A_use = A_nom
    else:
        K4_use = K4_est
        D_use = K4_est * 11.07
        if D_use > k1_nom - 0.01:
            D_use = k1_nom - 0.01
        if D_use < 0.05:
            D_use = 0.05
        A_use = k1_nom - D_use
    
    Delta_use = B_use * D_use - A_use * C_use
    if abs(Delta_use) < 1e-9:
        Delta_use = Delta_nom
        B_use, D_use, A_use, C_use = B_nom, D_nom, A_nom, C_nom
    
    S1 = C1 * math.sqrt(max(h1, 0.001))
    S2 = C2 * math.sqrt(max(h2, 0.001))
    
    d1 = S1 - B_use * v2 - A_use * v1
    d2 = S2 - D_use * v1 - C_use * v2
    
    v2_max = min(12.0, math.sqrt(upper_limit * 0.95) / max(K3_use, 1e-6))
    v1_max = min(12.0, math.sqrt(upper_limit * 0.95) / max(K4_use, 1e-6))
    
    K1 = v2_max * Delta_use + D_use * d1 - A_use * d2
    K2 = C_use * d1 - B_use * d2 - v1_max * Delta_use
    
    best_cost = 1e18
    best_h1 = h1_act
    best_h2 = h2_act
    best_Q = Q_target
    
    Q_min = max(0.0, Q_target - 6.0)
    Q_max_try = Q_target
    step_Q = 0.5
    Q_vals = []
    q = Q_min
    while q <= Q_max_try + 1e-9:
        Q_vals.append(q)
        q += step_Q
    if Q_vals and Q_vals[-1] < Q_max_try - 1e-9:
        Q_vals.append(Q_max_try)
    
    for Q in Q_vals:
        denom_low = B_use + C_use
        denom_high = D_use + A_use
        if abs(denom_low) < 1e-9 or abs(denom_high) < 1e-9:
            continue
        S1_low_v = (K2 + B_use * Q) / denom_low
        S1_high_v = (K1 + A_use * Q) / denom_high
        
        S1_min_safety = Q - C2 * math.sqrt(1.5)
        S1_max_safety = Q - C2 * math.sqrt(0.02)
        S1_min_sp = C1 * math.sqrt(max(sp_lo, 0.001))
        S1_max_sp = C1 * math.sqrt(max(sp_hi, 0.001))
        
        S1_min = max(S1_low_v, S1_min_safety, S1_min_sp, 0.0)
        S1_max = min(S1_high_v, S1_max_safety, S1_max_sp)
        if S1_min > S1_max + 1e-9:
            continue
        
        n_samples = 11
        for i in range(n_samples):
            if n_samples == 1:
                s1 = S1_min
            else:
                s1 = S1_min + (S1_max - S1_min) * i / (n_samples - 1)
            h1_cand = (s1 / C1) ** 2
            h2_cand = ((Q - s1) / C2) ** 2
            if h1_cand < sp_lo - 1e-6 or h1_cand > sp_hi + 1e-6:
                continue
            if h2_cand < 0.02 - 1e-6 or h2_cand > 1.5 + 1e-6:
                continue
            travel = 100.0 * (abs(h1_cand - h1_act) + abs(h2_cand - h2_act))
            band_pen = 200.0 * (max(0.0, band_lo - h2_cand) + max(0.0, h2_cand - band_hi))
            prod_pen = 10.0 * abs(Q - Q_target)
            total = travel + band_pen + prod_pen
            if total < best_cost:
                best_cost = total
                best_h1 = h1_cand
                best_h2 = h2_cand
                best_Q = Q
    
    if best_cost > 1e17:
        return {
            "diagnosis": "no feasible setpoint found, keeping current",
            "adjusted_setpoints": {"h1": h1_act, "h2": h2_act}
        }
    
    best_h1 = min(sp_hi, max(sp_lo, best_h1))
    best_h2 = min(sp_hi, max(sp_lo, best_h2))
    
    diag = "Q_eff=%.2f, h1=%.3f, h2=%.3f" % (best_Q, best_h1, best_h2)
    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"h1": best_h1, "h2": best_h2}
    }