def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    a1 = 0.0035
    a2 = 0.0030
    a3 = 0.0020
    a4 = 0.0025
    An = 0.20 * 0.00085
    Bn = 0.80 * 0.00095
    Cn = 0.20 * 0.00095
    Dn = 0.80 * 0.00085
    K1 = a1 * math.sqrt(2.0 * g)
    K2 = a2 * math.sqrt(2.0 * g)
    TG = 2.0 * g
    Qt = float(objectives['production_target'])
    Qtm = Qt / 1000.0
    h2lo = float(objectives['h2_band'][0])
    h2hi = float(objectives['h2_band'][1])
    Hup = float(objectives['upper_level_limit'])
    splo = float(objectives['setpoint_limits'][0])
    sphi = float(objectives['setpoint_limits'][1])
    last = telemetry_window[-1]
    h1 = float(last['h1'])
    h2 = float(last['h2'])
    h3 = float(last['h3'])
    h4 = float(last['h4'])
    v1 = float(last['v1'])
    v2 = float(last['v2'])
    h1a = float(active_setpoints['h1'])
    h2a = float(active_setpoints['h2'])
    n = len(telemetry_window)
    m = 15
    if n < m:
        m = n
    if m < 2:
        m = 2
    past = telemetry_window[n - m]
    dtt = float(last['time']) - float(past['time'])
    if dtt <= 0.0:
        dtt = 1.0
    s1 = (h1 - float(past['h1'])) / dtt
    s2 = (h2 - float(past['h2'])) / dtt
    s3 = (h3 - float(past['h3'])) / dtt
    s4 = (h4 - float(past['h4'])) / dtt
    sl = 0.05
    if s1 > sl:
        s1 = sl
    elif s1 < -sl:
        s1 = -sl
    if s2 > sl:
        s2 = sl
    elif s2 < -sl:
        s2 = -sl
    if s3 > sl:
        s3 = sl
    elif s3 < -sl:
        s3 = -sl
    if s4 > sl:
        s4 = sl
    elif s4 < -sl:
        s4 = -sl
    if h1 > 0.0:
        q1m = K1 * math.sqrt(h1)
    else:
        q1m = 0.0
    if h2 > 0.0:
        q2m = K2 * math.sqrt(h2)
    else:
        q2m = 0.0
    if h3 > 0.0:
        f3m = a3 * math.sqrt(TG * h3)
    else:
        f3m = 0.0
    if h4 > 0.0:
        f4m = a4 * math.sqrt(TG * h4)
    else:
        f4m = 0.0
    if v1 > 0.5:
        Aef = (q1m + s1 - f3m) / v1
        Def = (f4m + s4) / v1
    else:
        Aef = An
        Def = Dn
    if v2 > 0.5:
        Bef = (f3m + s3) / v2
        Cef = (q2m + s2 - f4m) / v2
    else:
        Bef = Bn
        Cef = Cn
    if Aef > 2.0 * An:
        Aef = 2.0 * An
    elif Aef < -2.0 * An:
        Aef = -2.0 * An
    if Cef > 2.0 * Cn:
        Cef = 2.0 * Cn
    elif Cef < -2.0 * Cn:
        Cef = -2.0 * Cn
    if Bef > 1.6 * Bn:
        Bef = 1.6 * Bn
    elif Bef < 0.2 * Bn:
        Bef = 0.2 * Bn
    if Def > 1.6 * Dn:
        Def = 1.6 * Dn
    elif Def < 0.2 * Dn:
        Def = 0.2 * Dn
    det = Aef * Cef - Bef * Def
    if det > -1e-9:
        Aef = An
        Bef = Bn
        Cef = Cn
        Def = Dn
        det = An * Cn - Bn * Dn
    Hcap = Hup - 0.015
    b_lo = h2lo + 0.005
    b_hi = h2hi - 0.005
    best = None
    best_h1 = h1a
    best_h2 = h2a
    h2c = 0.02
    while h2c <= 0.7001:
        q2c = K2 * math.sqrt(h2c)
        q1c = Qtm - q2c
        if q1c > 1e-6:
            h1c = (q1c / K1) ** 2
            v1c = (Cef * q1c - Bef * q2c) / det
            v2c = (Aef * q2c - Def * q1c) / det
            if v2c > 0.0:
                h3c = (Bef * v2c / a3) ** 2 / TG
            else:
                h3c = 0.0
            if v1c > 0.0:
                h4c = (Def * v1c / a4) ** 2 / TG
            else:
                h4c = 0.0
            c = 100.0 * (abs(h1c - h1a) + abs(h2c - h2a))
            if h3c > Hcap:
                c += 20000.0 * (h3c - Hcap)
            if h4c > Hcap:
                c += 20000.0 * (h4c - Hcap)
            if h2c > b_hi:
                c += 8000.0 * (h2c - b_hi)
            elif h2c < b_lo:
                c += 8000.0 * (b_lo - h2c)
            if v1c > 11.7:
                c += 2000.0 * (v1c - 11.7)
            elif v1c < 1.3:
                c += 2000.0 * (1.3 - v1c)
            if v2c > 11.7:
                c += 2000.0 * (v2c - 11.7)
            elif v2c < 1.3:
                c += 2000.0 * (1.3 - v2c)
            if h1c > 1.45:
                c += 20000.0 * (h1c - 1.45)
            elif h1c < 0.03:
                c += 20000.0 * (0.03 - h1c)
            if best is None or c < best:
                best = c
                best_h1 = h1c
                best_h2 = h2c
        h2c += 0.001
    if best_h1 < splo:
        best_h1 = splo
    elif best_h1 > sphi:
        best_h1 = sphi
    if best_h2 < splo:
        best_h2 = splo
    elif best_h2 > sphi:
        best_h2 = sphi
    diag = 'Qtar=%.2f sp=(%.3f,%.3f) gains %.2e/%.2e/%.2e/%.2e' % (Qt, best_h1, best_h2, Aef, Bef, Cef, Def)
    return {'diagnosis': diag, 'adjusted_setpoints': {'h1': best_h1, 'h2': best_h2}}
