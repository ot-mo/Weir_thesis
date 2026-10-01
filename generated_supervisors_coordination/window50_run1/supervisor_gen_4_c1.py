def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    c = math.sqrt(2.0 * 9.81)
    KC = 1000.0 * c
    r1 = 0.25
    r2 = 0.25
    
    try:
        h1a = float(active_setpoints["h1"])
        h2a = float(active_setpoints["h2"])
    except Exception:
        h1a = 0.30
        h2a = 0.35
    hold = {"diagnosis": "hold", "adjusted_setpoints": {"h1": h1a, "h2": h2a}}
    
    try:
        Q_t = float(objectives["production_target"])
        band = objectives["h2_band"]
        h2lo = float(band[0])
        h2hi = float(band[1])
        ulim = float(objectives["upper_level_limit"])
        lim = objectives["setpoint_limits"]
        splo = float(lim[0])
        sphi = float(lim[1])
        n = len(telemetry_window)
        if n < 6:
            return hold
        m = 6
        tail = telemetry_window[n-m:]
        
        def fit(key):
            vals = []
            for row in tail:
                vals.append(float(row[key]))
            mm = len(vals)
            if mm < 2:
                return vals[0], 0.0
            mt = (mm - 1) * 0.5
            num = 0.0
            den = 0.0
            s = 0.0
            for i in range(mm):
                d = i - mt
                num += d * vals[i]
                den += d * d
                s += vals[i]
            sl = num / den if den > 0.0 else 0.0
            mean = s / mm
            return mean + sl * (mm - 1 - mt), sl
        
        h1, sh1 = fit("h1")
        h2, sh2 = fit("h2")
        h3, sh3 = fit("h3")
        h4, sh4 = fit("h4")
        v1, sv1 = fit("v1")
        v2, sv2 = fit("v2")
    except Exception:
        return hold
    
    if h1 < 0.0: h1 = 0.0
    if h2 < 0.0: h2 = 0.0
    if h3 < 0.0: h3 = 0.0
    if h4 < 0.0: h4 = 0.0
    if v1 < 0.0: v1 = 0.0
    if v2 < 0.0: v2 = 0.0
    
    eps = 1e-9
    g2 = (a3 * KC * math.sqrt(h3) + 1000.0 * sh3) / v2 if v2 > eps else 0.0
    g1 = (a4 * KC * math.sqrt(h4) + 1000.0 * sh4) / v1 if v1 > eps else 0.0
    if g2 < 1e-6: g2 = 1e-6
    if g1 < 1e-6: g1 = 1e-6
    
    phi1 = r1 * g1 * v1
    phi2 = r2 * g2 * v2
    d1 = a1 * KC * math.sqrt(h1) + 1000.0 * sh1 - a3 * KC * math.sqrt(h3) - phi1
    d2 = a2 * KC * math.sqrt(h2) + 1000.0 * sh2 - a4 * KC * math.sqrt(h4) - phi2
    
    S = Q_t / KC
    if S <= 0.0:
        return hold
    
    h2_lo_lim = 0.02
    if splo > h2_lo_lim: h2_lo_lim = splo
    if h2lo > h2_lo_lim: h2_lo_lim = h2lo
    h2_hi_lim = 1.5
    if sphi < h2_hi_lim: h2_hi_lim = sphi
    if h2hi < h2_hi_lim: h2_hi_lim = h2hi
    h1_lo_lim = 0.02
    if splo > h1_lo_lim: h1_lo_lim = splo
    h1_hi_lim = 1.5
    if sphi < h1_hi_lim: h1_hi_lim = sphi
    
    def h1_from_h2(h2v):
        if h2v < 0.0:
            h2v = 0.0
        numer = S - a2 * math.sqrt(h2v)
        if numer <= 0.0:
            return 0.0
        return (numer / a1) ** 2
    
    h1_at_hi = h1_from_h2(h2_hi_lim)
    h1_at_lo = h1_from_h2(h2_lo_lim)
    lo = h1_at_hi if h1_at_hi > h1_lo_lim else h1_lo_lim
    hi = h1_at_lo if h1_at_lo < h1_hi_lim else h1_hi_lim
    if lo > hi:
        lo = h1_lo_lim
        hi = h1_hi_lim
    if hi < lo:
        hi = lo
    
    def evaluate(h1s):
        if h1s < 0.0:
            h1s = 0.0
        rem = S - a1 * math.sqrt(h1s)
        if rem <= 0.0:
            h2s = 0.0
        else:
            h2s = (rem / a2) ** 2
        A = KC * a1 * math.sqrt(h1s)
        B = KC * a2 * math.sqrt(h2s)
        den = 1.0 - r1 * r2
        X = ((A - d1) - r1 * (B - d2)) / den
        Y = ((B - d2) - r2 * (A - d1)) / den
        v2p = X / g2 if g2 > eps else 1e9
        v1p = Y / g1 if g1 > eps else 1e9
        h3p = (X / (KC * a3)) ** 2 if X > 0.0 else 0.0
        h4p = (Y / (KC * a4)) ** 2 if Y > 0.0 else 0.0
        return h2s, X, Y, v1p, v2p, h3p, h4p
    
    tiers = [
        (0.70, 0.70, 11.5, 1.5),
        (0.73, 0.73, 11.8, 1.2),
        (0.75, 0.75, 12.0, 1.0),
    ]
    
    best_sp = None
    for (h3lim, h4lim, vmax_t, vmin_t) in tiers:
        N = 121
        step = (hi - lo) / (N - 1) if N > 1 and hi > lo else 0.0
        local_best = None
        local_cost = None
        for k in range(N):
            h1s = lo + k * step if step > 0.0 else lo
            h2s, X, Y, v1p, v2p, h3p, h4p = evaluate(h1s)
            if h1s < h1_lo_lim - 1e-9 or h1s > h1_hi_lim + 1e-9:
                continue
            if h2s < h2_lo_lim - 1e-9 or h2s > h2_hi_lim + 1e-9:
                continue
            if h3p > h3lim + 1e-9 or h4p > h4lim + 1e-9:
                continue
            if v1p > vmax_t + 1e-9 or v2p > vmax_t + 1e-9:
                continue
            if v1p < vmin_t - 1e-9 or v2p < vmin_t - 1e-9:
                continue
            if not (v1p < 1e8 and v2p < 1e8):
                continue
            travel = abs(h1s - h1a) + abs(h2s - h2a)
            margin_cost = 0.0
            if h3p > h3lim - 0.02: margin_cost += 0.001
            if h4p > h4lim - 0.02: margin_cost += 0.001
            if v1p > vmax_t - 0.5: margin_cost += 0.001
            if v2p > vmax_t - 0.5: margin_cost += 0.001
            cost = travel + margin_cost
            if local_best is None or cost < local_cost - 1e-12:
                local_best = (h1s, h2s)
                local_cost = cost
        if local_best is not None:
            best_sp = local_best
            break
    
    if best_sp is None:
        N = 81
        step = (hi - lo) / (N - 1) if N > 1 and hi > lo else 0.0
        best_pen = None
        for k in range(N):
            h1s = lo + k * step if step > 0.0 else lo
            h2s, X, Y, v1p, v2p, h3p, h4p = evaluate(h1s)
            if h1s < h1_lo_lim - 1e-9 or h1s > h1_hi_lim + 1e-9:
                continue
            pen = 0.0
            if h1s < 0.02: pen += 10.0 * (0.02 - h1s) / 0.1
            if h1s > 1.5: pen += 10.0 * (h1s - 1.5) / 0.1
            if h2s < 0.02: pen += 10.0 * (0.02 - h2s) / 0.1
            if h2s > 1.5: pen += 10.0 * (h2s - 1.5) / 0.1
            if h2s < h2_lo_lim: pen += 1.0 * (h2_lo_lim - h2s) / 0.05
            if h2s > h2_hi_lim: pen += 1.0 * (h2s - h2_hi_lim) / 0.05
            if h3p > ulim: pen += 1.0 * (h3p - ulim) / 0.05
            if h4p > ulim: pen += 1.0 * (h4p - ulim) / 0.05
            if v1p > 12.0: pen += 0.3 * (v1p - 12.0) / 1.0
            if v2p > 12.0: pen += 0.3 * (v2p - 12.0) / 1.0
            if v1p < 1.0: pen += 0.3 * (1.0 - v1p) / 1.0
            if v2p < 1.0: pen += 0.3 * (1.0 - v2p) / 1.0
            pen += 0.01 * (abs(h1s - h1a) + abs(h2s - h2a))
            if best_pen is None or pen < best_pen:
                best_pen = pen
                best_sp = (h1s, h2s)
    
    if best_sp is None:
        return hold
    
    h1s, h2s = best_sp
    if h1s < h1_lo_lim: h1s = h1_lo_lim
    if h1s > h1_hi_lim: h1s = h1_hi_lim
    if h2s < h2_lo_lim: h2s = h2_lo_lim
    if h2s > h2_hi_lim: h2s = h2_hi_lim
    
    A_a = KC * a1 * math.sqrt(max(h1a, 0.0))
    B_a = KC * a2 * math.sqrt(max(h2a, 0.0))
    Q_a = A_a + B_a
    
    def feasible_pair(h1c, h2c, h3lim, h4lim, vmax_t, vmin_t):
        A = KC * a1 * math.sqrt(max(h1c, 0.0))
        B = KC * a2 * math.sqrt(max(h2c, 0.0))
        den = 1.0 - r1 * r2
        X = ((A - d1) - r1 * (B - d2)) / den
        Y = ((B - d2) - r2 * (A - d1)) / den
        v2p = X / g2 if g2 > eps else 1e9
        v1p = Y / g1 if g1 > eps else 1e9
        h3p = (X / (KC * a3)) ** 2 if X > 0.0 else 0.0
        h4p = (Y / (KC * a4)) ** 2 if Y > 0.0 else 0.0
        if h3p > h3lim or h4p > h4lim:
            return False
        if v1p > vmax_t or v2p > vmax_t:
            return False
        if v1p < vmin_t or v2p < vmin_t:
            return False
        return True
    
    if abs(Q_a - Q_t) < 0.05 and feasible_pair(h1a, h2a, 0.70, 0.70, 11.5, 1.5):
        return hold
    
    travel = abs(h1s - h1a) + abs(h2s - h2a)
    if travel < 0.004:
        return hold
    
    h2s_c, X, Y, v1p, v2p, h3p, h4p = evaluate(h1s)
    diag = "Q_t=%.2f h3p=%.2f h4p=%.2f v1p=%.1f v2p=%.1f" % (Q_t, h3p, h4p, v1p, v2p)
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": h1s, "h2": h2s}}
