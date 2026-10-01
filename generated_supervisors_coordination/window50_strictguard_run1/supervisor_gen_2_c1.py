def supervise(telemetry_window, active_setpoints, objectives):
    try:
        g = 9.81
        sqrt2g = math.sqrt(2.0 * g)
        a1 = 0.0035
        a2 = 0.003
        a3 = 0.002
        a4 = 0.0025
        c1 = a1 * sqrt2g * 1000.0
        c2 = a2 * sqrt2g * 1000.0
        c3 = a3 * sqrt2g * 1000.0
        c4 = a4 * sqrt2g * 1000.0
        beta1_nom = c4 * math.sqrt(0.306) / 9.0
        beta2_nom = c3 * math.sqrt(0.617) / 9.16
        last = telemetry_window[-1]
        h1 = last['h1']
        h2 = last['h2']
        h3 = last['h3']
        h4 = last['h4']
        v1 = last['v1']
        v2 = last['v2']
        target = objectives['production_target']
        band_low, band_high = objectives['h2_band']
        upper_limit = objectives['upper_level_limit']
        sp_lo, sp_hi = objectives['setpoint_limits']
        active_h1 = active_setpoints['h1']
        active_h2 = active_setpoints['h2']
        q1_meas = c1 * math.sqrt(max(0.0, h1))
        q2_meas = c2 * math.sqrt(max(0.0, h2))
        r3_meas = c3 * math.sqrt(max(0.0, h3))
        r4_meas = c4 * math.sqrt(max(0.0, h4))
        idx = len(telemetry_window) - 1
        if idx >= 4:
            old = telemetry_window[idx - 4]
            dh3 = (h3 - old['h3']) / 4.0
            dh4 = (h4 - old['h4']) / 4.0
        else:
            dh3 = 0.0
            dh4 = 0.0
        beta1 = (r4_meas + 1000.0 * dh4) / v1 if v1 > 0.5 else beta1_nom
        beta2 = (r3_meas + 1000.0 * dh3) / v2 if v2 > 0.5 else beta2_nom
        if beta1 <= 0.01:
            beta1 = beta1_nom
        if beta2 <= 0.01:
            beta2 = beta2_nom
        alpha1 = (q1_meas - r3_meas) / r4_meas if r4_meas > 0.5 else 0.25
        alpha2 = (q2_meas - r4_meas) / r3_meas if r3_meas > 0.5 else 0.25
        alpha1 = min(2.0, max(-0.5, alpha1))
        alpha2 = min(2.0, max(-0.5, alpha2))
        denom = 1.0 - alpha1 * alpha2
        if abs(denom) < 0.05:
            denom = 0.05 if denom >= 0 else -0.05
        margin = 0.005
        q2_lo = c2 * math.sqrt(max(0.0, band_low + margin))
        q2_hi = c2 * math.sqrt(max(0.0, band_high - margin))
        q1_min_sp = c1 * math.sqrt(max(0.0, sp_lo))
        q1_max_sp = c1 * math.sqrt(max(0.0, sp_hi))
        q2_lo = max(q2_lo, target - q1_max_sp)
        q2_hi = min(q2_hi, target - q1_min_sp)
        if q2_lo > q2_hi:
            q2_lo = c2 * math.sqrt(max(0.0, band_low))
            q2_hi = c2 * math.sqrt(max(0.0, band_high))
        q2_lo = max(q2_lo, 0.0)
        q2_hi = min(q2_hi, target)
        if q2_lo > q2_hi:
            q2_lo = target * 0.4807
            q2_hi = target * 0.4807
        best_cost = None
        best_q2 = target * 0.4807
        step = 0.02
        n = int((q2_hi - q2_lo) / step) + 1
        for i in range(n + 1):
            q2 = q2_lo + i * step
            if q2 > q2_hi + 1e-9:
                break
            q1 = target - q2
            if q1 < 0.0:
                continue
            h1_sp = (q1 / c1) ** 2
            h2_sp = (q2 / c2) ** 2
            if h1_sp < sp_lo - 1e-9 or h1_sp > sp_hi + 1e-9:
                continue
            if h2_sp < sp_lo - 1e-9 or h2_sp > sp_hi + 1e-9:
                continue
            travel = abs(h1_sp - active_h1) + abs(h2_sp - active_h2)
            penalty = 0.0
            if h2_sp < band_low:
                penalty += (band_low - h2_sp) * 5000.0
            if h2_sp > band_high:
                penalty += (h2_sp - band_high) * 5000.0
            if h1_sp < 0.02:
                penalty += (0.02 - h1_sp) * 10000.0
            if h1_sp > 1.5:
                penalty += (h1_sp - 1.5) * 10000.0
            r3 = (q1 - alpha1 * q2) / denom
            r4 = q2 - alpha2 * r3
            if r3 < 0.0:
                r3 = 0.0
            if r4 < 0.0:
                r4 = 0.0
            h3_pred = (r3 / c3) ** 2
            h4_pred = (r4 / c4) ** 2
            v1_pred = r4 / beta1
            v2_pred = r3 / beta2
            if h3_pred > upper_limit:
                penalty += (h3_pred - upper_limit) * 2000.0
            if h4_pred > upper_limit:
                penalty += (h4_pred - upper_limit) * 2000.0
            v_margin = 11.8
            if v1_pred > v_margin:
                penalty += (v1_pred - v_margin) * 2000.0
            if v2_pred > v_margin:
                penalty += (v2_pred - v_margin) * 2000.0
            cost = 100.0 * travel + penalty
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_q2 = q2
        best_q1 = target - best_q2
        h1_sp = (best_q1 / c1) ** 2
        h2_sp = (best_q2 / c2) ** 2
        h1_sp = min(sp_hi, max(sp_lo, h1_sp))
        h2_sp = min(sp_hi, max(sp_lo, h2_sp))
        diag = 'split q2=%.2f L/s -> h1=%.3f,h2=%.3f' % (best_q2, h1_sp, h2_sp)
        return {
            'diagnosis': diag,
            'adjusted_setpoints': {'h1': float(h1_sp), 'h2': float(h2_sp)},
        }
    except Exception:
        nom_q1 = c1 * math.sqrt(0.30)
        nom_q2 = c2 * math.sqrt(0.35)
        nom_prod = nom_q1 + nom_q2
        scale = (objectives.get('production_target', 16.35286638873749) / nom_prod) ** 2
        lo, hi = objectives.get('setpoint_limits', [0.02, 1.5])
        h1 = min(hi, max(lo, 0.30 * scale))
        h2 = min(hi, max(lo, 0.35 * scale))
        return {
            'diagnosis': 'fallback nominal scaled recipe',
            'adjusted_setpoints': {'h1': float(h1), 'h2': float(h2)},
        }
