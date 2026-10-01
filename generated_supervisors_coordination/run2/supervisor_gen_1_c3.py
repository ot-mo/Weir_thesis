def supervise(telemetry_window, active_setpoints, objectives):
    G = 9.81
    S2G = (2.0 * G) ** 0.5
    A1 = 0.0035
    A2 = 0.003
    A3 = 0.002
    A4 = 0.0025
    K1 = 0.00085
    K2 = 0.00095
    GAM1 = 0.20
    GAM2 = 0.20
    Q_t = float(objectives['production_target'])
    band = objectives['h2_band']
    band_lo = float(band[0])
    band_hi = float(band[1])
    uplim = float(objectives['upper_level_limit'])
    sph = objectives['setpoint_limits']
    sp_lo = float(sph[0])
    sp_hi = float(sph[1])
    h1s = float(active_setpoints['h1'])
    h2s = float(active_setpoints['h2'])
    n = len(telemetry_window)
    if n < 1:
        return {'diagnosis': 'no telemetry; holding setpoints',
                'adjusted_setpoints': {'h1': h1s, 'h2': h2s}}
    m = 2 if n >= 2 else 1
    sh1 = 0.0
    sh2 = 0.0
    sh3 = 0.0
    sh4 = 0.0
    sv1 = 0.0
    sv2 = 0.0
    for idx in range(n - m, n):
        s = telemetry_window[idx]
        sh1 += float(s['h1'])
        sh2 += float(s['h2'])
        sh3 += float(s['h3'])
        sh4 += float(s['h4'])
        sv1 += float(s['v1'])
        sv2 += float(s['v2'])
    h1 = sh1 / m
    h2 = sh2 / m
    h3 = sh3 / m
    h4 = sh4 / m
    v1 = sv1 / m
    v2 = sv2 / m

    def sq(x):
        if x <= 0.0:
            return 0.0
        return x ** 0.5

    d1 = A1 * S2G * sq(h1) - (1.0 - GAM2) * K2 * v2 - GAM1 * K1 * v1
    d2 = A2 * S2G * sq(h2) - (1.0 - GAM1) * K1 * v1 - GAM2 * K2 * v2
    Qm3 = Q_t / 1000.0

    def h2_of(h1c):
        r = Qm3 - A1 * S2G * sq(h1c)
        if r <= 1e-9:
            return None
        return (r / A2) ** 2 / (2.0 * G)

    def h1_of(h2c):
        r = Qm3 - A2 * S2G * sq(h2c)
        if r <= 1e-9:
            return None
        return (r / A1) ** 2 / (2.0 * G)

    lo1 = max(sp_lo, 0.05)
    hi1 = min(sp_hi, 1.40)
    t = h1_of(band_hi - 0.02)
    if t is not None and t > lo1:
        lo1 = t
    t = h1_of(band_lo + 0.02)
    if t is not None and t < hi1:
        hi1 = t
    if hi1 <= lo1 + 1e-6:
        lo1 = max(sp_lo, 0.05)
        hi1 = min(sp_hi, 1.40)

    h3_safe = min(0.70, uplim - 0.05)
    h4_safe = min(0.70, uplim - 0.05)
    v_hi = 11.0
    v_lo = 2.0

    def cost_of(h1c, h2c):
        F1 = A1 * S2G * sq(h1c) - d1
        F2 = A2 * S2G * sq(h2c) - d2
        v1c = (4.0 * F2 - F1) / (3.0 * K1)
        v2c = (4.0 * F1 - F2) / (3.0 * K2)
        if v2c > 0.0:
            h3c = ((1.0 - GAM2) * K2 * v2c / A3) ** 2 / (2.0 * G)
        else:
            h3c = 0.0
        if v1c > 0.0:
            h4c = ((1.0 - GAM1) * K1 * v1c / A4) ** 2 / (2.0 * G)
        else:
            h4c = 0.0
        c = 100.0 * (abs(h1c - h1s) + abs(h2c - h2s))
        if h3c > h3_safe:
            c += 8000.0 * (h3c - h3_safe) * (h3c - h3_safe)
        if h4c > h4_safe:
            c += 8000.0 * (h4c - h4_safe) * (h4c - h4_safe)
        if h2c > band_hi:
            c += 3000.0 * (h2c - band_hi) * (h2c - band_hi)
        if h2c < band_lo:
            c += 3000.0 * (band_lo - h2c) * (band_lo - h2c)
        if v2c > v_hi:
            c += 6000.0 * (v2c - v_hi) * (v2c - v_hi)
        if v1c > v_hi:
            c += 6000.0 * (v1c - v_hi) * (v1c - v_hi)
        if v2c < v_lo:
            c += 6000.0 * (v_lo - v2c) * (v_lo - v2c)
        if v1c < v_lo:
            c += 6000.0 * (v_lo - v1c) * (v_lo - v1c)
        return c, h3c, h4c, v1c, v2c

    cand = []
    N = 61
    if hi1 > lo1:
        for i in range(N):
            cand.append(lo1 + (hi1 - lo1) * i / (N - 1.0))
    cand.append(h1s)
    t = h1_of(h2s)
    if t is not None and sp_lo <= t <= sp_hi:
        cand.append(t)

    best = None
    for h1c in cand:
        h2c = h2_of(h1c)
        if h2c is None:
            continue
        if h2c < 0.03 or h2c > 1.45:
            continue
        h1q = min(sp_hi, max(sp_lo, h1c))
        h2q = min(sp_hi, max(sp_lo, h2c))
        cc = cost_of(h1q, h2q)
        if best is None or cc[0] < best[0]:
            best = (cc[0], h1q, h2q, cc[1], cc[3], cc[4])

    if best is None:
        return {'diagnosis': 'no feasible split; holding setpoints',
                'adjusted_setpoints': {'h1': h1s, 'h2': h2s}}

    h1n = best[1]
    h2n = best[2]
    if abs(h1n - h1s) < 0.003 and abs(h2n - h2s) < 0.003:
        h1n = h1s
        h2n = h2s
    h1n = min(sp_hi, max(sp_lo, h1n))
    h2n = min(sp_hi, max(sp_lo, h2n))
    diag = ('Qsp=%.2f sp=(%.3f,%.3f) meas h3=%.3f v2=%.2f pred h3=%.3f v2=%.2f'
            % (Q_t, h1n, h2n, h3, v2, best[3], best[5]))
    return {'diagnosis': diag, 'adjusted_setpoints': {'h1': h1n, 'h2': h2n}}