def supervise(telemetry_window, active_setpoints, objectives):
    a1=0.0035; a2=0.003; a3=0.002; a4=0.0025
    k1=0.00085; k2=0.00095
    g=9.81
    c=math.sqrt(2.0*g)
    A1=a1*c; A2=a2*c; A3=a3*c; A4=a4*c
    gamma1=0.2; gamma2=0.2
    ratio1=gamma1/(1.0-gamma1)
    ratio2=gamma2/(1.0-gamma2)
    
    try:
        h1a = float(active_setpoints["h1"])
        h2a = float(active_setpoints["h2"])
    except Exception:
        h1a = 0.30; h2a = 0.35
    fallback = {"diagnosis": "hold setpoints", "adjusted_setpoints": {"h1": h1a, "h2": h2a}}
    
    try:
        Q_t = float(objectives["production_target"])
        band = objectives["h2_band"]
        h2lo = float(band[0]); h2hi = float(band[1])
        ulim = float(objectives["upper_level_limit"])
        lim = objectives["setpoint_limits"]
        splo = float(lim[0]); sphi = float(lim[1])
        
        n = len(telemetry_window)
        if n < 1:
            return fallback
        
        sum_h3 = 0.0; sum_h4 = 0.0
        max_h3 = 0.0; max_h4 = 0.0
        a_sum = 0.0; c_sum = 0.0
        for row in telemetry_window:
            h3 = float(row["h3"]); h4 = float(row["h4"])
            v1 = float(row["v1"]); v2 = float(row["v2"])
            if h3 < 0.0: h3 = 0.0
            if h4 < 0.0: h4 = 0.0
            if v1 <= 0.0: v1 = 0.001
            if v2 <= 0.0: v2 = 0.001
            sum_h3 += h3; sum_h4 += h4
            if h3 > max_h3: max_h3 = h3
            if h4 > max_h4: max_h4 = h4
            a_sum += A3 * math.sqrt(h3) / v2
            c_sum += A4 * math.sqrt(h4) / v1
        N = float(n)
        avg_h3 = sum_h3 / N
        avg_h4 = sum_h4 / N
        a_est = a_sum / N
        c_est = c_sum / N
        
        if a_est <= 0.0 or c_est <= 0.0:
            a_est = (1.0-gamma2)*k2
            c_est = (1.0-gamma1)*k1
        b_est = c_est * ratio1
        d_est = a_est * ratio2
        
        sum_d1 = 0.0; sum_d2 = 0.0
        for row in telemetry_window:
            h1 = float(row["h1"]); h2 = float(row["h2"])
            v1 = float(row["v1"]); v2 = float(row["v2"])
            if h1 < 0.0: h1 = 0.0
            if h2 < 0.0: h2 = 0.0
            if v1 <= 0.0: v1 = 0.001
            if v2 <= 0.0: v2 = 0.001
            q1 = A1 * math.sqrt(h1)
            q2 = A2 * math.sqrt(h2)
            sum_d1 += q1 - a_est * v2 - b_est * v1
            sum_d2 += q2 - c_est * v1 - d_est * v2
        d1_est = sum_d1 / N
        d2_est = sum_d2 / N
        
        det = b_est * d_est - a_est * c_est
        if abs(det) < 1e-12:
            return fallback
        
        q_target = Q_t / 1000.0
        
        peak_factor_h3 = max_h3 / avg_h3 if avg_h3 > 1e-6 else 1.0
        peak_factor_h4 = max_h4 / avg_h4 if avg_h4 > 1e-6 else 1.0
        
        h1_min = 0.02
        h1_max = 1.5
        step = 0.005
        best_cost = None
        best_h1 = h1a
        best_h2 = h2a
        
        h = h1_min
        while h <= h1_max + 1e-9:
            q1 = A1 * math.sqrt(h)
            if q1 > q_target:
                h += step
                continue
            q2 = q_target - q1
            if q2 < 0.0:
                h += step
                continue
            h2 = (q2 / A2) ** 2
            rhs1 = q1 - d1_est
            rhs2 = q2 - d2_est
            v1 = (rhs1 * d_est - a_est * rhs2) / det
            v2 = (b_est * rhs2 - c_est * rhs1) / det
            
            pred_h3 = 0.0; pred_h4 = 0.0
            if v2 > 0.0:
                pred_h3 = (a_est * v2 / A3) ** 2
            if v1 > 0.0:
                pred_h4 = (c_est * v1 / A4) ** 2
            peak_h3 = pred_h3 * peak_factor_h3
            peak_h4 = pred_h4 * peak_factor_h4
            
            travel = abs(h - h1a) + abs(h2 - h2a)
            penalty = 0.0
            if h < 0.02: penalty += 10000.0 + (0.02 - h)*1000.0
            if h > 1.5: penalty += 10000.0 + (h - 1.5)*1000.0
            if h2 < 0.02: penalty += 10000.0 + (0.02 - h2)*1000.0
            if h2 > 1.5: penalty += 10000.0 + (h2 - 1.5)*1000.0
            if h2 < h2lo: penalty += 10000.0 + (h2lo - h2)*1000.0
            if h2 > h2hi: penalty += 10000.0 + (h2 - h2hi)*1000.0
            if peak_h3 > ulim: penalty += 10000.0 + (peak_h3 - ulim)*1000.0
            if peak_h4 > ulim: penalty += 10000.0 + (peak_h4 - ulim)*1000.0
            if v1 < 1.0: penalty += 5000.0 + (1.0 - v1)*1000.0
            if v1 > 12.0: penalty += 5000.0 + (v1 - 12.0)*1000.0
            if v2 < 1.0: penalty += 5000.0 + (1.0 - v2)*1000.0
            if v2 > 12.0: penalty += 5000.0 + (v2 - 12.0)*1000.0
            if v1 <= 0.0 or v2 <= 0.0:
                penalty += 20000.0
            if h < splo: penalty += 10000.0
            if h > sphi: penalty += 10000.0
            if h2 < splo: penalty += 10000.0
            if h2 > sphi: penalty += 10000.0
            
            cost = 100.0 * travel + penalty
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_h1 = h
                best_h2 = h2
            h += step
        
        h1s = best_h1
        h2s = best_h2
        if h1s < splo: h1s = splo
        if h1s > sphi: h1s = sphi
        if h2s < splo: h2s = splo
        if h2s > sphi: h2s = sphi
        
        if abs(h1s - h1a) < 0.002 and abs(h2s - h2a) < 0.002:
            h1s = h1a
            h2s = h2a
        
        diag = "scan h1=%.3f h2=%.3f Q=%.2f" % (h1s, h2s, Q_t)
        return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1s, "h2": h2s}}
    except Exception:
        return fallback