def supervise(telemetry_window, active_setpoints, nominal_targets):
    def _num(src, key, default):
        try:
            if isinstance(src, dict):
                v = src.get(key, default)
            else:
                return float(default)
            if isinstance(v, bool):
                return float(default)
            return float(v)
        except (TypeError, ValueError):
            return float(default)

    t1_sp = _num(active_setpoints, 'tank1', 0.0)
    t2_sp = _num(active_setpoints, 'tank2', 0.0)
    nom1 = _num(nominal_targets, 'tank1', t1_sp)
    nom2 = _num(nominal_targets, 'tank2', t2_sp)

    if isinstance(telemetry_window, (list, tuple)):
        n = len(telemetry_window)
    else:
        n = 0

    if n == 0:
        return {
            'diagnosis': 'no telemetry available',
            'adjusted_setpoints': {'tank1': t1_sp, 'tank2': t2_sp},
            'anomaly_flags': {'tank1': False, 'tank2': False},
        }

    def series(tank, key):
        out = []
        for step in telemetry_window:
            v = 0.0
            if isinstance(step, dict):
                d = step.get(tank)
                if isinstance(d, dict):
                    x = d.get(key, 0.0)
                    if isinstance(x, bool):
                        x = 0.0
                    elif isinstance(x, (int, float)):
                        v = float(x)
            out.append(v)
        return out

    eff1 = series('tank1', 'pump_effort')
    eff2 = series('tank2', 'pump_effort')
    err1 = series('tank1', 'error')
    err2 = series('tank2', 'error')

    def median(xs):
        if not xs:
            return 0.0
        s = sorted(xs)
        m = len(s)
        if m % 2 == 1:
            return s[m // 2]
        return 0.5 * (s[m // 2 - 1] + s[m // 2])

    def quantile(xs, q):
        if not xs:
            return 0.0
        s = sorted(xs)
        m = len(s)
        if m == 1:
            return s[0]
        if q <= 0.0:
            return s[0]
        if q >= 1.0:
            return s[-1]
        pos = q * (m - 1)
        lo = int(pos)
        hi = lo + 1
        if hi >= m:
            return s[-1]
        fr = pos - lo
        return s[lo] * (1.0 - fr) + s[hi] * fr

    def roll_med(xs, win):
        out = []
        m = len(xs)
        for i in range(m):
            a = i - win + 1
            if a < 0:
                a = 0
            out.append(median(xs[a:i + 1]))
        return out

    def tail(xs, kk):
        if kk <= 0:
            return []
        if len(xs) <= kk:
            return xs
        return xs[len(xs) - kk:]

    def mean_abs(xs):
        if not xs:
            return 0.0
        t = 0.0
        for x in xs:
            t += abs(x)
        return t / float(len(xs))

    def frac_above(xs, thr):
        if not xs:
            return 0.0
        c = 0
        for x in xs:
            if x > thr:
                c += 1
        return c / float(len(xs))

    def scale_for(sp, nom):
        if nom > 0.0 and sp > 0.05:
            sc = nom / sp
            if sc < 0.4:
                sc = 0.4
            if sc > 3.0:
                sc = 3.0
            return sc
        return 1.0

    sc1 = scale_for(t1_sp, nom1)
    sc2 = scale_for(t2_sp, nom2)
    ne1 = [e * sc1 for e in eff1]
    ne2 = [e * sc2 for e in eff2]

    k = min(8, n)
    h = max(3, min(5, n))
    w = min(14, n)
    wl = min(20, n)

    def analyze(nes, errs, abs_ceiling):
        rm = roll_med(nes, 5)
        ref = quantile(rm, 0.15)
        if ref < 0.0:
            ref = 0.0
        te = median(tail(nes, k))
        dev = te - ref
        ae = mean_abs(tail(errs, k))
        det_bar = max(0.45, 0.20 * ref)
        thr = ref + det_bar
        f_dev = frac_above(tail(nes, w), thr)
        raw = bool((dev > 0.85)
                   or (dev > 0.45 and ae > 0.10)
                   or (f_dev >= 0.70)
                   or (te > abs_ceiling))
        rec_bar = max(0.30, 0.14 * ref)
        rec_med = median(tail(nes, h))
        rec = bool((rec_med <= ref + rec_bar)
                   and (ae <= 0.20)
                   and (rec_med <= abs_ceiling - 0.05))
        f_long = frac_above(tail(nes, wl), thr)
        persist_long = bool(f_long >= 0.75)
        return {
            'ref': ref, 'te': te, 'dev': dev, 'ae': ae,
            'raw': raw, 'rec': rec, 'persist_long': persist_long,
        }

    a1 = analyze(ne1, err1, 2.50)
    a2 = analyze(ne2, err2, 2.10)

    raw1 = a1['raw']
    raw2 = a2['raw']

    upstream1 = bool(raw1 or a1['dev'] > 0.40)

    resid2 = a2['dev'] - 0.55 * max(a1['dev'], 0.0)
    resid_ok = bool(resid2 > max(0.30, 0.20 * a2['ref']))
    ceil_ok = bool(a2['te'] > 2.10)
    independent2 = bool(a2['persist_long'] and (resid_ok or ceil_ok))

    cascade = bool(upstream1 and raw2 and (not independent2))

    tank1_anom = bool(raw1 and not a1['rec'])
    tank2_anom = bool(raw2 and (not a2['rec']) and (not cascade))

    LOWER_STEP = 0.3
    MAX_DEPRESS = 1.0
    RESTORE_STEP = 0.6

    if tank1_anom:
        cand1 = max(nom1 - MAX_DEPRESS, t1_sp - LOWER_STEP)
        if cand1 > t1_sp:
            cand1 = t1_sp
        new1 = cand1
        diag1 = 'tank1 anomaly (setpoint-scaled effort above own baseline); setpoint depressed'
    elif (t1_sp < nom1) and (a1['dev'] < 0.35) and (a1['ae'] < 0.20):
        new1 = min(nom1, t1_sp + RESTORE_STEP)
        diag1 = 'tank1 clear; restoring setpoint toward nominal'
    else:
        new1 = t1_sp
        diag1 = 'tank1 nominal'

    if tank2_anom:
        cand2 = max(nom2 - MAX_DEPRESS, t2_sp - LOWER_STEP)
        if cand2 > t2_sp:
            cand2 = t2_sp
        new2 = cand2
        diag2 = 'tank2 anomaly (persistent and not bounded by upstream excess); setpoint depressed'
    elif cascade:
        new2 = t2_sp
        diag2 = 'tank2 rise bounded by upstream tank1 excess (coupling, not flagged)'
    elif (t2_sp < nom2) and (a2['dev'] < 0.35) and (a2['ae'] < 0.20):
        new2 = min(nom2, t2_sp + RESTORE_STEP)
        diag2 = 'tank2 clear; restoring setpoint toward nominal'
    else:
        new2 = t2_sp
        diag2 = 'tank2 nominal'

    return {
        'diagnosis': diag1 + '; ' + diag2,
        'adjusted_setpoints': {'tank1': new1, 'tank2': new2},
        'anomaly_flags': {'tank1': tank1_anom, 'tank2': tank2_anom},
    }
