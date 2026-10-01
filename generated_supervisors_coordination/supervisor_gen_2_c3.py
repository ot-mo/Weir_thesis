def supervise(telemetry_window, active_setpoints, objectives):
    sq2g = 4.42944691807002
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1_nom = 0.00085
    k2_nom = 0.00095
    gam1 = 0.20
    gam2 = 0.20

    n = len(telemetry_window)
    if n < 10:
        return {'diagnosis': 'insufficient data, holding', 'adjusted_setpoints': {'h1': float(active_setpoints['h1']), 'h2': float(active_setpoints['h2'])}}

    m = 10
    win = telemetry_window[n-m:n]
    s1 = s2 = s3 = s4 = sv1 = sv2 = 0.0
    for r in win:
        s1 += r['h1']; s2 += r['h2']; s3 += r['h3']; s4 += r['h4']; sv1 += r['v1']; sv2 += r['v2']
    h1a = s1/m; h2a = s2/m; h3a = s3/m; h4a = s4/m; v1a = sv1/m; v2a = sv2/m

    def fl(a, h):
        if h <= 0.0: return 0.0
        return a * sq2g * math.sqrt(h)

    k2_eff = k2_nom
    if v2a > 0.5:
        k2_eff = fl(a3, h3a) / ((1.0 - gam2) * v2a)
    k1_eff = k1_nom
    if v1a > 0.5:
        k1_eff = fl(a4, h4a) / ((1.0 - gam1) * v1a)

    if k2_eff < 0.5 * k2_nom: k2_eff = 0.5 * k2_nom
    if k2_eff > 1.5 * k2_nom: k2_eff = 1.5 * k2_nom
    if k1_eff < 0.5 * k1_nom: k1_eff = 0.5 * k1_nom
    if k1_eff > 1.5 * k1_nom: k1_eff = 1.5 * k1_nom

    d1 = fl(a1, h1a) - fl(a3, h3a) - gam1 * k1_eff * v1a
    d2 = fl(a2, h2a) - fl(a4, h4a) - gam2 * k2_eff * v2a

    T_L = objectives['production_target']
    Q_target = T_L / 1000.0
    if Q_target <= 0.0: Q_target = 0.0163529

    sp_lo, sp_hi = objectives['setpoint_limits']
    h2_lo, h2_hi = objectives['h2_band']
    uplim = objectives['upper_level_limit']
    h3_limit = uplim - 0.02
    h4_limit = uplim - 0.02

    h1_curr = active_setpoints['h1']
    h2_curr = active_setpoints['h2']

    best_cost = 1e12
    best_h1 = h1_curr
    best_h2 = h2_curr

    nQ = 15
    nF = 40
    for iQ in range(nQ):
        Q_try = Q_target * (1.0 - 0.01 * iQ)
        if Q_try < 0.8 * Q_target: break
        for iF in range(nF + 1):
            F1 = Q_try * (iF / float(nF))
            F2 = Q_try - F1
            if F2 < 0.0: continue
            x1 = F1 / (sq2g * a1)
            x2 = F2 / (sq2g * a2)
            h1_sp = x1 * x1
            h2_sp = x2 * x2

            if h1_sp < 0.02 or h1_sp > 1.5: continue
            if h2_sp < 0.02 or h2_sp > 1.5: continue
            if h1_sp < sp_lo or h1_sp > sp_hi: continue
            if h2_sp < sp_lo or h2_sp > sp_hi: continue

            A11 = gam1 * k1_eff
            A12 = (1.0 - gam2) * k2_eff
            A21 = (1.0 - gam1) * k1_eff
            A22 = gam2 * k2_eff
            b1 = F1 - d1
            b2 = F2 - d2
            det = A11 * A22 - A12 * A21
            if abs(det) < 1e-12: continue
            v1 = (b1 * A22 - b2 * A12) / det
            v2 = (A11 * b2 - A21 * b1) / det

            h3_pred = 0.0
            if v2 > 0.0:
                h3_pred = ((1.0 - gam2) * k2_eff * v2 / (a3 * sq2g)) ** 2
            h4_pred = 0.0
            if v1 > 0.0:
                h4_pred = ((1.0 - gam1) * k1_eff * v1 / (a4 * sq2g)) ** 2

            pen = 0.0
            if v1 < 1.0: pen += 10000.0 * (1.0 - v1)
            if v1 > 12.0: pen += 10000.0 * (v1 - 12.0)
            if v2 < 1.0: pen += 10000.0 * (1.0 - v2)
            if v2 > 12.0: pen += 10000.0 * (v2 - 12.0)
            if h3_pred > h3_limit: pen += 10000.0 * (h3_pred - h3_limit)
            if h4_pred > h4_limit: pen += 10000.0 * (h4_pred - h4_limit)
            if h2_sp < h2_lo: pen += 2000.0 * (h2_lo - h2_sp)
            if h2_sp > h2_hi: pen += 2000.0 * (h2_sp - h2_hi)

            travel = abs(h1_sp - h1_curr) + abs(h2_sp - h2_curr)
            prod_err = abs(Q_try * 1000.0 - T_L)
            cost = 100.0 * travel + 20.0 * prod_err + pen

            if cost < best_cost:
                best_cost = cost
                best_h1 = h1_sp
                best_h2 = h2_sp

    if best_cost > 1e11:
        best_h1 = h1_curr
        best_h2 = h2_curr

    if best_h1 < sp_lo: best_h1 = sp_lo
    if best_h1 > sp_hi: best_h1 = sp_hi
    if best_h2 < sp_lo: best_h2 = sp_lo
    if best_h2 > sp_hi: best_h2 = sp_hi

    if abs(best_h1 - h1_curr) < 0.002 and abs(best_h2 - h2_curr) < 0.002:
        best_h1 = h1_curr
        best_h2 = h2_curr

    diag = 'adaptive k1=' + str(round(k1_eff,6)) + ' k2=' + str(round(k2_eff,6)) + ' d1=' + str(round(d1,6)) + ' d2=' + str(round(d2,6)) + ' -> h1=' + str(round(best_h1,3)) + ' h2=' + str(round(best_h2,3))
    return {'diagnosis': diag, 'adjusted_setpoints': {'h1': float(best_h1), 'h2': float(best_h2)}}