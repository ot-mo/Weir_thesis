def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    g = 9.81
    gamma1_nom = 0.20
    gamma2_nom = 0.20
    
    Q_target = objectives["production_target"]
    q = Q_target / 1000.0
    lo_sp, hi_sp = objectives["setpoint_limits"]
    h2_band = objectives["h2_band"]
    upper_limit = objectives["upper_level_limit"]
    
    N = len(telemetry_window)
    K = min(90, N)
    start = N - K
    h1s = [telemetry_window[i]["h1"] for i in range(start, N)]
    h2s = [telemetry_window[i]["h2"] for i in range(start, N)]
    h3s = [telemetry_window[i]["h3"] for i in range(start, N)]
    h4s = [telemetry_window[i]["h4"] for i in range(start, N)]
    v1s = [telemetry_window[i]["v1"] for i in range(start, N)]
    v2s = [telemetry_window[i]["v2"] for i in range(start, N)]
    
    A_vals = []
    B_vals = []
    F1_vals = []
    F2_vals = []
    v1_vals = []
    v2_vals = []
    for i in range(5, K):
        dh1 = (h1s[i] - h1s[i-5]) / 5.0
        dh2 = (h2s[i] - h2s[i-5]) / 5.0
        dh3 = (h3s[i] - h3s[i-5]) / 5.0
        dh4 = (h4s[i] - h4s[i-5]) / 5.0
        u1 = a1 * math.sqrt(2*g*max(0, h1s[i]))
        u2 = a2 * math.sqrt(2*g*max(0, h2s[i]))
        u3 = a3 * math.sqrt(2*g*max(0, h3s[i]))
        u4 = a4 * math.sqrt(2*g*max(0, h4s[i]))
        v1 = v1s[i]
        v2 = v2s[i]
        if v1 > 0.1:
            B_vals.append((dh4 + u4) / v1)
        if v2 > 0.1:
            A_vals.append((dh3 + u3) / v2)
        F1 = dh1 + u1 - u3
        F2 = dh2 + u2 - u4
        F1_vals.append(F1)
        F2_vals.append(F2)
        v1_vals.append(v1)
        v2_vals.append(v2)
    
    if len(A_vals) > 0:
        A_est = sum(A_vals)/len(A_vals)
    else:
        A_est = (1-gamma2_nom)*0.00095
    if len(B_vals) > 0:
        B_est = sum(B_vals)/len(B_vals)
    else:
        B_est = (1-gamma1_nom)*0.00085
    
    def linreg(x, y):
        n = len(x)
        if n < 10:
            return None, None
        mx = sum(x)/n
        my = sum(y)/n
        cov = 0.0
        var = 0.0
        for i in range(n):
            dx = x[i] - mx
            cov += dx * (y[i] - my)
            var += dx * dx
        if var < 1e-8:
            return None, None
        C = cov/var
        d = my - C*mx
        return C, d
    
    C_est, d1_est = linreg(v1_vals, F1_vals)
    if C_est is None or C_est < 0:
        k1_est = B_est / (1 - gamma1_nom) if (1-gamma1_nom) > 0 else 0
        C_est = gamma1_nom * k1_est
        mean_F1 = sum(F1_vals)/len(F1_vals) if F1_vals else 0
        mean_v1 = sum(v1_vals)/len(v1_vals) if v1_vals else 0
        d1_est = mean_F1 - C_est * mean_v1
    
    D_est, d2_est = linreg(v2_vals, F2_vals)
    if D_est is None or D_est < 0:
        k2_est = A_est / (1 - gamma2_nom) if (1-gamma2_nom) > 0 else 0
        D_est = gamma2_nom * k2_est
        mean_F2 = sum(F2_vals)/len(F2_vals) if F2_vals else 0
        mean_v2 = sum(v2_vals)/len(v2_vals) if v2_vals else 0
        d2_est = mean_F2 - D_est * mean_v2
    
    det = C_est * D_est - A_est * B_est
    
    sp_h1 = active_setpoints["h1"]
    sp_h2 = active_setpoints["h2"]
    
    best_cost = 1e18
    best_h1 = sp_h1
    best_h2 = sp_h2
    
    h1_min = max(lo_sp, 0.05)
    h1_max = min(hi_sp, 0.8)
    candidates = [(sp_h1, sp_h2)]
    steps = int((h1_max - h1_min) / 0.01) + 1
    for k in range(steps):
        h1_cand = h1_min + 0.01 * k
        if h1_cand > h1_max:
            break
        u1_star = a1 * math.sqrt(2*g*h1_cand)
        if u1_star >= q:
            continue
        u2_star = q - u1_star
        if u2_star <= 0:
            continue
        h2_cand = (u2_star / a2)**2 / (2*g)
        candidates.append((h1_cand, h2_cand))
    
    for (h1_cand, h2_cand) in candidates:
        h1_c = min(hi_sp, max(lo_sp, h1_cand))
        u1_c = a1 * math.sqrt(2*g*h1_c)
        if u1_c >= q:
            continue
        u2_req = q - u1_c
        h2_req = (u2_req / a2)**2 / (2*g)
        h2_c = min(hi_sp, max(lo_sp, h2_req))
        
        u1_c = a1 * math.sqrt(2*g*h1_c)
        u2_c = a2 * math.sqrt(2*g*h2_c)
        
        if abs(det) < 1e-14:
            continue
        
        rhs1 = u1_c - d1_est
        rhs2 = u2_c - d2_est
        v1_pred = (rhs1 * D_est - A_est * rhs2) / det
        v2_pred = (C_est * rhs2 - B_est * rhs1) / det
        
        cost = 0.0
        travel = abs(h1_c - sp_h1) + abs(h2_c - sp_h2)
        cost += 100.0 * travel
        
        if v1_pred < 1.0:
            cost += 5000.0 * (1.0 - v1_pred)
        elif v1_pred > 12.0:
            cost += 5000.0 * (v1_pred - 12.0)
        if v2_pred < 1.0:
            cost += 5000.0 * (1.0 - v2_pred)
        elif v2_pred > 12.0:
            cost += 5000.0 * (v2_pred - 12.0)
        
        h3_pred = (A_est * v2_pred / a3)**2 / (2*g) if v2_pred > 0 else 0
        h4_pred = (B_est * v1_pred / a4)**2 / (2*g) if v1_pred > 0 else 0
        if h3_pred > upper_limit:
            cost += 5000.0 * (h3_pred - upper_limit)
        if h4_pred > upper_limit:
            cost += 5000.0 * (h4_pred - upper_limit)
        
        if h2_c < h2_band[0]:
            cost += 1000.0 * (h2_band[0] - h2_c)
        elif h2_c > h2_band[1]:
            cost += 1000.0 * (h2_c - h2_band[1])
        
        if h1_c < 0.02 or h1_c > 1.5:
            cost += 100000.0
        if h2_c < 0.02 or h2_c > 1.5:
            cost += 100000.0
        
        Q_c = (u1_c + u2_c) * 1000.0
        cost += 10.0 * abs(Q_c - Q_target)
        
        if cost < best_cost:
            best_cost = cost
            best_h1 = h1_c
            best_h2 = h2_c
    
    best_h1 = min(hi_sp, max(lo_sp, best_h1))
    best_h2 = min(hi_sp, max(lo_sp, best_h2))
    
    diagnosis = f"model-based: A={A_est:.5f} B={B_est:.5f} C={C_est:.5f} D={D_est:.5f} d1={d1_est:.5f} d2={d2_est:.5f}; set h1={best_h1:.3f} h2={best_h2:.3f}"
    return {
        "diagnosis": diagnosis,
        "adjusted_setpoints": {"h1": best_h1, "h2": best_h2},
    }