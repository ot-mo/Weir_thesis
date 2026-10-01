def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    B_nom = 0.00076
    C_nom = 0.00068
    RAT = 0.25

    Qt = float(objectives['production_target'])
    band = objectives['h2_band']
    band_lo = float(band[0]) + 0.003
    band_hi = float(band[1]) - 0.003
    Ulim = float(objectives['upper_level_limit']) - 0.010
    lim = objectives['setpoint_limits']
    sp_lo = float(lim[0])
    sp_hi = float(lim[1])
    h1_cur = float(active_setpoints['h1'])
    h2_cur = float(active_setpoints['h2'])

    tw = telemetry_window
    n = len(tw)
    if n < 5:
        return {'diagnosis': 'insufficient telemetry', 'adjusted_setpoints': {'h1': h1_cur, 'h2': h2_cur}}

    s_v1 = 0.0
    s_v2 = 0.0
    s_q1 = 0.0
    s_q2 = 0.0
    s_q3 = 0.0
    s_q4 = 0.0
    for smp in tw:
        s_v1 += smp['v1']
        s_v2 += smp['v2']
        s_q1 += a1 * math.sqrt(2.0 * g * smp['h1'])
        s_q2 += a2 * math.sqrt(2.0 * g * smp['h2'])
        s_q3 += a3 * math.sqrt(2.0 * g * smp['h3'])
        s_q4 += a4 * math.sqrt(2.0 * g * smp['h4'])
    m_v1 = s_v1 / n
    m_v2 = s_v2 / n
    m_q1 = s_q1 / n
    m_q2 = s_q2 / n
    m_q3 = s_q3 / n
    m_q4 = s_q4 / n

    dt = tw[n - 1]['time'] - tw[0]['time']
    if dt > 0.5:
        sl1 = (tw[n - 1]['h1'] - tw[0]['h1']) / dt
        sl2 = (tw[n - 1]['h2'] - tw[0]['h2']) / dt
        sl3 = (tw[n - 1]['h3'] - tw[0]['h3']) / dt
        sl4 = (tw[n - 1]['h4'] - tw[0]['h4']) / dt
    else:
        sl1 = 0.0
        sl2 = 0.0
        sl3 = 0.0
        sl4 = 0.0

    if m_v2 > 0.5:
        alpha = (m_q3 + sl3) / m_v2
    else:
        alpha = B_nom
    if alpha < 0.5 * B_nom:
        alpha = 0.5 * B_nom
    if alpha > 1.6 * B_nom:
        alpha = 1.6 * B_nom
    if m_v1 > 0.5:
        beta = (m_q4 + sl4) / m_v1
    else:
        beta = C_nom
    if beta < 0.5 * C_nom:
        beta = 0.5 * C_nom
    if beta > 1.6 * C_nom:
        beta = 1.6 * C_nom

    A_eff = RAT * beta
    B_eff = alpha
    C_eff = beta
    D_eff = RAT * alpha

    d1 = sl1 + m_q1 - B_eff * m_v2 + sl3 - A_eff * m_v1
    d2 = sl2 + m_q2 - C_eff * m_v1 + sl4 - D_eff * m_v2
    if d1 > 0.006:
        d1 = 0.006
    if d1 < -0.006:
        d1 = -0.006
    if d2 > 0.006:
        d2 = 0.006
    if d2 < -0.006:
        d2 = -0.006

    det = A_eff * D_eff - B_eff * C_eff
    if det > -1e-10:
        return {'diagnosis': 'degenerate model', 'adjusted_setpoints': {'h1': h1_cur, 'h2': h2_cur}}

    def cost_of(h1c, h2c):
        r1 = a1 * math.sqrt(2.0 * g * h1c) - d1
        r2 = a2 * math.sqrt(2.0 * g * h2c) - d2
        v1 = (r1 * D_eff - B_eff * r2) / det
        v2 = (A_eff * r2 - C_eff * r1) / det
        if v1 < 1.0:
            v1 = 1.0
        elif v1 > 12.0:
            v1 = 12.0
        if v2 < 1.0:
            v2 = 1.0
        elif v2 > 12.0:
            v2 = 12.0
        q1a = A_eff * v1 + B_eff * v2 + d1
        q2a = C_eff * v1 + D_eff * v2 + d2
        if q1a < 0.0:
            q1a = 0.0
        if q2a < 0.0:
            q2a = 0.0
        x = q1a / a1
        h1a = x * x / (2.0 * g)
        x = q2a / a2
        h2a = x * x / (2.0 * g)
        x = B_eff * v2
        h3a = x * x / (2.0 * g * a3 * a3)
        x = C_eff * v1
        h4a = x * x / (2.0 * g * a4 * a4)
        c = abs((q1a + q2a) * 1000.0 - Qt)
        if h2a < band_lo or h2a > band_hi:
            c += 2.0
        if h3a > Ulim or h4a > Ulim:
            c += 2.0
        if h1a < 0.025 or h1a > 1.48 or h2a < 0.025 or h2a > 1.48:
            c += 10.0
        c += abs(h1c - h1_cur) + abs(h2c - h2_cur)
        return c

    best_h1 = h1_cur
    best_h2 = h2_cur
    best_c = cost_of(h1_cur, h2_cur)

    g_lo = sp_lo
    if g_lo < 0.02:
        g_lo = 0.02
    g_hi = sp_hi
    if g_hi > 1.4:
        g_hi = 1.4

    h1 = g_lo
    while h1 <= g_hi + 1e-9:
        h2 = g_lo
        while h2 <= g_hi + 1e-9:
            c = cost_of(h1, h2)
            if c < best_c:
                best_c = c
                best_h1 = h1
                best_h2 = h2
            h2 += 0.05
        h1 += 0.05

    for step in (0.01, 0.002, 0.0005, 0.0001):
        b1 = best_h1
        b2 = best_h2
        k = -4
        while k <= 4:
            h1 = b1 + k * step
            if h1 < sp_lo:
                h1 = sp_lo
            if h1 > sp_hi:
                h1 = sp_hi
            k2 = -4
            while k2 <= 4:
                h2 = b2 + k2 * step
                if h2 < sp_lo:
                    h2 = sp_lo
                if h2 > sp_hi:
                    h2 = sp_hi
                c = cost_of(h1, h2)
                if c < best_c:
                    best_c = c
                    best_h1 = h1
                    best_h2 = h2
                k2 += 1
            k += 1

    dh1 = best_h1 - h1_cur
    dh2 = best_h2 - h2_cur
    cap = 0.05
    if dh1 > cap:
        dh1 = cap
    if dh1 < -cap:
        dh1 = -cap
    if dh2 > cap:
        dh2 = cap
    if dh2 < -cap:
        dh2 = -cap
    if abs(dh1) < 0.0025 and abs(dh2) < 0.0025:
        dh1 = 0.0
        dh2 = 0.0

    nh1 = h1_cur + dh1
    nh2 = h2_cur + dh2
    if nh1 < sp_lo:
        nh1 = sp_lo
    if nh1 > sp_hi:
        nh1 = sp_hi
    if nh2 < sp_lo:
        nh2 = sp_lo
    if nh2 > sp_hi:
        nh2 = sp_hi

    diag = ('target ' + str(round(Qt, 2)) + ' L/s; sp=(' + str(round(nh1, 3)) + ','
            + str(round(nh2, 3)) + '); d1=' + str(round(d1 * 1000.0, 2))
            + ' L/s d2=' + str(round(d2 * 1000.0, 2)) + ' L/s')
    return {'diagnosis': diag, 'adjusted_setpoints': {'h1': nh1, 'h2': nh2}}
