def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    c = math.sqrt(2.0 * g)
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095

    try:
        h1a = float(active_setpoints['h1'])
        h2a = float(active_setpoints['h2'])
    except Exception:
        h1a = 0.30
        h2a = 0.35
    fallback = {'diagnosis': 'hold setpoints', 'adjusted_setpoints': {'h1': h1a, 'h2': h2a}}

    try:
        Q_t = float(objectives['production_target'])
        band = objectives['h2_band']
        h2_lo_b = float(band[0])
        h2_hi_b = float(band[1])
        ulim = float(objectives['upper_level_limit'])
        lim = objectives['setpoint_limits']
        splo = float(lim[0])
        sphi = float(lim[1])
    except Exception:
        return fallback

    n = len(telemetry_window)
    if n < 1:
        return fallback

    m = 25
    if n < m:
        m = n
    tail = telemetry_window[n-m:]

    def fit(key):
        vals = []
        for row in tail:
            vals.append(float(row[key]))
        mm = len(vals)
        if mm < 2:
            return vals[-1], 0.0
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
        val_end = mean + sl * ((mm - 1) - mt)
        return val_end, sl

    try:
        h1f, sh1 = fit('h1')
        h2f, sh2 = fit('h2')
        h3f, sh3 = fit('h3')
        h4f, sh4 = fit('h4')
        v1f, sv1 = fit('v1')
        v2f, sv2 = fit('v2')
    except Exception:
        return fallback

    h1f = max(0.0, h1f)
    h2f = max(0.0, h2f)
    h3f = max(0.0, h3f)
    h4f = max(0.0, h4f)
    v1f = max(0.0, v1f)
    v2f = max(0.0, v2f)

    if h1a < splo: h1a = splo
    if h1a > sphi: h1a = sphi
    if h2a < splo: h2a = splo
    if h2a > sphi: h2a = sphi

    h1_lo_safe = max(0.02, splo)
    h1_hi_safe = min(1.5, sphi)
    h2_lo_safe = max(0.02, splo, h2_lo_b)
    h2_hi_safe = min(1.5, sphi, h2_hi_b)
    if h2_hi_safe - h2_lo_safe > 0.04:
        h2_lo_safe += 0.005
        h2_hi_safe -= 0.005
    if h1_hi_safe - h1_lo_safe > 0.04:
        h1_lo_safe += 0.002
        h1_hi_safe -= 0.002

    Q1_lo_safe = 1000.0*a1*c*math.sqrt(h1_lo_safe)
    Q1_hi_safe = 1000.0*a1*c*math.sqrt(h1_hi_safe)
    Q2_lo_safe = 1000.0*a2*c*math.sqrt(h2_lo_safe)
    Q2_hi_safe = 1000.0*a2*c*math.sqrt(h2_hi_safe)

    Q1_lo = Q1_lo_safe
    if Q_t - Q2_hi_safe > Q1_lo:
        Q1_lo = Q_t - Q2_hi_safe
    Q1_hi = Q1_hi_safe
    if Q_t - Q2_lo_safe < Q1_hi:
        Q1_hi = Q_t - Q2_lo_safe
    if Q1_lo < 0.0:
        Q1_lo = 0.0
    if Q1_hi < 0.0:
        Q1_hi = 0.0
    if Q1_hi > Q_t:
        Q1_hi = Q_t
    if Q1_lo > Q_t:
        Q1_lo = Q_t

    Q1a = 1000.0*a1*c*math.sqrt(max(h1a, 0.0))
    Q2a = 1000.0*a2*c*math.sqrt(max(h2a, 0.0))
    total_a = Q1a + Q2a
    target_changed = False
    if total_a > 1e-6 and abs(total_a - Q_t) > 0.05:
        target_changed = True
        s = Q_t / total_a
        h1b = h1a * s * s
        h2b = h2a * s * s
    else:
        h1b = h1a
        h2b = h2a

    def clamp_h(h, lo, hi):
        if h < lo: return lo
        if h > hi: return hi
        return h

    h1b = clamp_h(h1b, h1_lo_safe, h1_hi_safe)
    h2b = clamp_h(h2b, h2_lo_safe, h2_hi_safe)
    Q1b = 1000.0*a1*c*math.sqrt(h1b)
    Q2b = 1000.0*a2*c*math.sqrt(h2b)
    tot_b = Q1b + Q2b
    if tot_b > 1e-6 and abs(tot_b - Q_t) > 0.02:
        sb = Q_t / tot_b
        h1b = clamp_h(h1b * sb * sb, h1_lo_safe, h1_hi_safe)
        h2b = clamp_h(h2b * sb * sb, h2_lo_safe, h2_hi_safe)
        Q1b = 1000.0*a1*c*math.sqrt(h1b)
        Q2b = 1000.0*a2*c*math.sqrt(h2b)

    margin3 = 0.05
    margin4 = 0.05
    h3_t = ulim - margin3
    if h3_t < 0.0: h3_t = 0.0
    h4_t = ulim - margin4
    if h4_t < 0.0: h4_t = 0.0

    h3_pred = h3f
    h4_pred = h4f
    if h3f > 0.0:
        tmp = math.sqrt(h3f) + sh3/(a3*c)
        if tmp < 0.0: tmp = 0.0
        h3_pred = tmp * tmp
    if h4f > 0.0:
        tmp = math.sqrt(h4f) + sh4/(a4*c)
        if tmp < 0.0: tmp = 0.0
        h4_pred = tmp * tmp

    v2_hi = 10.5
    v1_hi = 10.5

    Q1_cap = Q1_hi
    Q1_floor = Q1_lo

    if h3_pred > h3_t and v2f > 1e-6 and h3_pred > 1e-9:
        r = math.sqrt(h3_t / h3_pred)
        v2_t = v2f * r
        dv2 = v2_t - v2f
        dQ1 = dv2 * (k2 * 0.6) * 1000.0
        cand = Q1b + dQ1
        if cand < Q1_cap:
            Q1_cap = cand
    if h4_pred > h4_t and v1f > 1e-6 and h4_pred > 1e-9:
        r = math.sqrt(h4_t / h4_pred)
        v1_t = v1f * r
        dv1 = v1_t - v1f
        dQ1 = -dv1 * (k1 * 0.6) * 1000.0
        cand = Q1b + dQ1
        if cand > Q1_floor:
            Q1_floor = cand
    if v2f > v2_hi:
        dv2 = v2_hi - v2f
        dQ1 = dv2 * (k2 * 0.6) * 1000.0
        cand = Q1b + dQ1
        if cand < Q1_cap:
            Q1_cap = cand
    if v1f > v1_hi:
        dv1 = v1_hi - v1f
        dQ1 = -dv1 * (k1 * 0.6) * 1000.0
        cand = Q1b + dQ1
        if cand > Q1_floor:
            Q1_floor = cand

    Q1_new = Q1b
    if Q1_new > Q1_cap:
        Q1_new = Q1_cap
    if Q1_new < Q1_floor:
        Q1_new = Q1_floor
    if Q1_new > Q1_hi:
        Q1_new = Q1_hi
    if Q1_new < Q1_lo:
        Q1_new = Q1_lo
    if Q1_new < 0.0:
        Q1_new = 0.0
    if Q1_new > Q_t:
        Q1_new = Q_t
    Q2_new = Q_t - Q1_new

    h1_new = (Q1_new / (1000.0*a1*c)) ** 2
    h2_new = (Q2_new / (1000.0*a2*c)) ** 2
    h1_new = clamp_h(h1_new, h1_lo_safe, h1_hi_safe)
    h2_new = clamp_h(h2_new, h2_lo_safe, h2_hi_safe)

    if target_changed:
        max_step = 0.15
    else:
        max_step = 0.03

    dh1 = h1_new - h1a
    dh2 = h2_new - h2a
    if dh1 > max_step: h1_new = h1a + max_step
    if dh1 < -max_step: h1_new = h1a - max_step
    if dh2 > max_step: h2_new = h2a + max_step
    if dh2 < -max_step: h2_new = h2a - max_step

    if abs(h1_new - h1a) < 0.0015 and abs(h2_new - h2a) < 0.0015:
        h1_new = h1a
        h2_new = h2a

    h1_new = clamp_h(h1_new, splo, sphi)
    h2_new = clamp_h(h2_new, splo, sphi)

    diag = 'Q_t=%.2f h3p=%.2f h4p=%.2f v1=%.1f v2=%.1f' % (Q_t, h3_pred, h4_pred, v1f, v2f)
    return {'diagnosis': diag, 'adjusted_setpoints': {'h1': h1_new, 'h2': h2_new}}