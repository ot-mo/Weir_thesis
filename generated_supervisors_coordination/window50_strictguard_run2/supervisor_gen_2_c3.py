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
    root2g = math.sqrt(2.0 * g)
    
    Q_target = objectives['production_target'] / 1000.0
    h2_low, h2_high = objectives['h2_band']
    upper_limit = objectives['upper_level_limit']
    sp_low, sp_high = objectives['setpoint_limits']
    safety_low = 0.02
    safety_high = 1.5
    
    if not telemetry_window:
        return {'diagnosis': 'no telemetry', 'adjusted_setpoints': {'h1': active_setpoints['h1'], 'h2': active_setpoints['h2']}}
    
    last = telemetry_window[-1]
    h1 = last['h1']
    h2 = last['h2']
    h3 = last['h3']
    h4 = last['h4']
    v1 = last['v1']
    v2 = last['v2']
    
    def slope(values, times):
        n = len(values)
        if n < 2:
            return 0.0
        m = min(n, 11)
        x = times[-m:]
        y = values[-m:]
        mean_x = sum(x) / m
        mean_y = sum(y) / m
        num = 0.0
        den = 0.0
        for i in range(m):
            dx = x[i] - mean_x
            num += dx * (y[i] - mean_y)
            den += dx * dx
        if den == 0.0:
            return 0.0
        return num / den
    
    times = [s['time'] for s in telemetry_window]
    h1s = [s['h1'] for s in telemetry_window]
    h2s = [s['h2'] for s in telemetry_window]
    h3s = [s['h3'] for s in telemetry_window]
    h4s = [s['h4'] for s in telemetry_window]
    
    dh1_dt = slope(h1s, times)
    dh2_dt = slope(h2s, times)
    dh3_dt = slope(h3s, times)
    dh4_dt = slope(h4s, times)
    
    q1 = a1 * root2g * math.sqrt(max(0.0, h1))
    q2 = a2 * root2g * math.sqrt(max(0.0, h2))
    q3 = a3 * root2g * math.sqrt(max(0.0, h3))
    q4 = a4 * root2g * math.sqrt(max(0.0, h4))
    
    denom2 = (1.0 - gamma2) * v2
    if denom2 > 1e-6:
        k2_eff = (q3 + dh3_dt) / denom2
    else:
        k2_eff = k2
    denom1 = (1.0 - gamma1) * v1
    if denom1 > 1e-6:
        k1_eff = (q4 + dh4_dt) / denom1
    else:
        k1_eff = k1
    k1_eff = max(0.0003, min(0.0015, k1_eff))
    k2_eff = max(0.0003, min(0.0015, k2_eff))
    
    d1 = dh1_dt + q1 - q3 - gamma1 * k1_eff * v1
    d2 = dh2_dt + q2 - q4 - gamma2 * k2_eff * v2
    d1 = max(-0.006, min(0.006, d1))
    d2 = max(-0.006, min(0.006, d2))
    
    h1_min = max(safety_low, sp_low, 0.02)
    h1_max = min(safety_high, sp_high, 1.2)
    if Q_target > 0.0:
        h1_qlim = (Q_target / (a1 * root2g))**2
        h1_max = min(h1_max, h1_qlim * 0.995)
    if h1_min > h1_max:
        h1_min, h1_max = h1_max, h1_min
    
    best_cost = None
    best_h1 = active_setpoints['h1']
    best_h2 = active_setpoints['h2']
    
    steps = 200
    for i in range(steps + 1):
        h1_c = h1_min + (h1_max - h1_min) * i / steps
        q1_c = a1 * root2g * math.sqrt(max(0.0, h1_c))
        q2_c = Q_target - q1_c
        if q2_c <= 1e-6:
            continue
        h2_c = (q2_c / (a2 * root2g))**2
        if h2_c < safety_low or h2_c > safety_high:
            continue
        if h2_c < sp_low or h2_c > sp_high:
            continue
        
        A = gamma1 * k1_eff
        B = (1.0 - gamma2) * k2_eff
        C = gamma2 * k2_eff
        D = (1.0 - gamma1) * k1_eff
        det = A * C - B * D
        if abs(det) < 1e-12:
            continue
        rhs1 = q1_c - d1
        rhs2 = q2_c - d2
        v1_c = (rhs1 * C - B * rhs2) / det
        v2_c = (A * rhs2 - D * rhs1) / det
        
        if v2_c > 0.0:
            h3_c = ((1.0 - gamma2) * k2_eff * v2_c / (a3 * root2g))**2
        else:
            h3_c = 0.0
        if v1_c > 0.0:
            h4_c = ((1.0 - gamma1) * k1_eff * v1_c / (a4 * root2g))**2
        else:
            h4_c = 0.0
        
        cost = 0.0
        cost += 100.0 * (abs(h1_c - active_setpoints['h1']) + abs(h2_c - active_setpoints['h2']))
        if h3_c > upper_limit:
            cost += 10000.0 * (h3_c - upper_limit)**2
        if h4_c > upper_limit:
            cost += 10000.0 * (h4_c - upper_limit)**2
        if h2_c < h2_low:
            cost += 10000.0 * (h2_low - h2_c)**2
        elif h2_c > h2_high:
            cost += 10000.0 * (h2_c - h2_high)**2
        if h1_c < safety_low:
            cost += 20000.0 * (safety_low - h1_c)**2
        elif h1_c > safety_high:
            cost += 20000.0 * (h1_c - safety_high)**2
        if h2_c < safety_low:
            cost += 20000.0 * (safety_low - h2_c)**2
        elif h2_c > safety_high:
            cost += 20000.0 * (h2_c - safety_high)**2
        if v1_c < 1.0:
            cost += 5000.0 * (1.0 - v1_c)**2
        elif v1_c > 12.0:
            cost += 5000.0 * (v1_c - 12.0)**2
        if v2_c < 1.0:
            cost += 5000.0 * (1.0 - v2_c)**2
        elif v2_c > 12.0:
            cost += 5000.0 * (v2_c - 12.0)**2
        
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_h1 = h1_c
            best_h2 = h2_c
    
    if best_cost is None:
        best_h1 = active_setpoints['h1']
        best_h2 = active_setpoints['h2']
    
    best_h1 = max(safety_low, min(safety_high, best_h1))
    best_h2 = max(safety_low, min(safety_high, best_h2))
    best_h1 = max(sp_low, min(sp_high, best_h1))
    best_h2 = max(sp_low, min(sp_high, best_h2))
    
    return {
        'diagnosis': 'model-based split; d1=%.4f d2=%.4f k1_eff=%.5f k2_eff=%.5f' % (d1, d2, k1_eff, k2_eff),
        'adjusted_setpoints': {'h1': best_h1, 'h2': best_h2},
    }