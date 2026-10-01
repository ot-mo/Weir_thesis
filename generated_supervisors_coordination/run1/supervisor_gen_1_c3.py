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

    s = telemetry_window[-1]
    h1 = s['h1']
    h2 = s['h2']
    h3 = s['h3']
    h4 = s['h4']
    v1 = s['v1']
    v2 = s['v2']

    sp_h1 = active_setpoints['h1']
    sp_h2 = active_setpoints['h2']

    target = objectives['production_target']
    Qs = target / 1000.0

    h2_band = objectives['h2_band']
    upper_limit = objectives['upper_level_limit']
    sp_limits = objectives['setpoint_limits']
    sp_lo = sp_limits[0]
    sp_hi = sp_limits[1]

    c3_nom = (1.0 - gamma2) * k2
    c4_nom = (1.0 - gamma1) * k1
    if v2 > 0.1:
        c3 = a3 * math.sqrt(2.0 * g * max(0.0, h3)) / v2
    else:
        c3 = c3_nom
    if v1 > 0.1:
        c4 = a4 * math.sqrt(2.0 * g * max(0.0, h4)) / v1
    else:
        c4 = c4_nom
    c3 = min(2.0 * c3_nom, max(0.5 * c3_nom, c3))
    c4 = min(2.0 * c4_nom, max(0.5 * c4_nom, c4))

    F3 = c3 * v2
    F4 = c4 * v1
    x_meas = a1 * math.sqrt(2.0 * g * max(0.0, h1))
    y_meas = a2 * math.sqrt(2.0 * g * max(0.0, h2))
    direct1 = (gamma1 / (1.0 - gamma1)) * F4
    direct2 = (gamma2 / (1.0 - gamma2)) * F3
    inflow1 = F3 + direct1
    inflow2 = F4 + direct2
    d1 = x_meas - inflow1
    d2 = y_meas - inflow2
    d1 = min(0.005, max(-0.005, d1))
    d2 = min(0.005, max(-0.005, d2))

    def h_from_x(x):
        if x <= 0.0:
            return 0.0
        return (x / a1) ** 2 / (2.0 * g)

    def h_from_y(y):
        if y <= 0.0:
            return 0.0
        return (y / a2) ** 2 / (2.0 * g)

    def q1(h):
        return a1 * math.sqrt(2.0 * g * max(0.0, h))

    def q2(h):
        return a2 * math.sqrt(2.0 * g * max(0.0, h))

    h2_min = max(0.02, sp_lo)
    h2_max = min(1.5, sp_hi)
    y_min = q2(h2_min)
    y_max = q2(h2_max)
    x_max = q1(min(1.5, sp_hi))
    y_min = max(y_min, Qs - x_max)
    x_min = q1(max(0.02, sp_lo))
    y_max = min(y_max, Qs - x_min)
    if y_min > y_max:
        y_min = min(y_max, q2(sp_h2))
        y_max = max(y_min, q2(sp_h2))
    if y_max <= y_min:
        y_max = y_min + 1e-6

    N = 201
    best_cost = None
    best_h1 = sp_h1
    best_h2 = sp_h2

    safe_h3 = upper_limit * 0.96
    safe_h4 = upper_limit * 0.96
    safe_v = 11.0
    h2_low = h2_band[0]
    h2_high = h2_band[1]

    for i in range(N):
        y = y_min + (y_max - y_min) * i / (N - 1)
        x = Qs - y
        if x <= 0.0:
            continue
        h1_c = h_from_x(x)
        h2_c = h_from_y(y)

        num1 = (y - d2) - 0.25 * (x - d1)
        num2 = (x - d1) - 0.25 * (y - d2)
        if c4 < 1e-12 or c3 < 1e-12:
            continue
        v1_c = num1 / (0.9375 * c4)
        v2_c = num2 / (0.9375 * c3)

        F3_c = c3 * v2_c
        F4_c = c4 * v1_c
        h3_c = (F3_c / a3) ** 2 / (2.0 * g) if F3_c > 0.0 else 0.0
        h4_c = (F4_c / a4) ** 2 / (2.0 * g) if F4_c > 0.0 else 0.0

        cost = 100.0 * (abs(h1_c - sp_h1) + abs(h2_c - sp_h2))

        if h1_c < 0.02:
            cost += 20000.0 * (0.02 - h1_c)
        if h1_c > 1.5:
            cost += 20000.0 * (h1_c - 1.5)
        if h2_c < 0.02:
            cost += 20000.0 * (0.02 - h2_c)
        if h2_c > 1.5:
            cost += 20000.0 * (h2_c - 1.5)

        if h1_c < sp_lo:
            cost += 20000.0 * (sp_lo - h1_c)
        if h1_c > sp_hi:
            cost += 20000.0 * (h1_c - sp_hi)
        if h2_c < sp_lo:
            cost += 20000.0 * (sp_lo - h2_c)
        if h2_c > sp_hi:
            cost += 20000.0 * (h2_c - sp_hi)

        if h2_c < h2_low:
            cost += 2000.0 * (h2_low - h2_c)
        if h2_c > h2_high:
            cost += 2000.0 * (h2_c - h2_high)

        if h3_c > safe_h3:
            cost += 2000.0 * (h3_c - safe_h3)
        if h4_c > safe_h4:
            cost += 2000.0 * (h4_c - safe_h4)

        if v1_c > safe_v:
            cost += 2000.0 * (v1_c - safe_v)
        if v2_c > safe_v:
            cost += 2000.0 * (v2_c - safe_v)
        if v1_c < 1.0:
            cost += 2000.0 * (1.0 - v1_c)
        if v2_c < 1.0:
            cost += 2000.0 * (1.0 - v2_c)

        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_h1 = h1_c
            best_h2 = h2_c

    best_h1 = min(sp_hi, max(sp_lo, best_h1))
    best_h2 = min(sp_hi, max(sp_lo, best_h2))

    diag = 'model-based split: target=%.2f, h3=%.2f, h4=%.2f, v1=%.1f, v2=%.1f' % (target, h3, h4, v1, v2)
    return {
        'diagnosis': diag,
        'adjusted_setpoints': {'h1': best_h1, 'h2': best_h2},
    }
