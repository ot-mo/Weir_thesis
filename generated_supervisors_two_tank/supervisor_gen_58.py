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

    n = len(telemetry_window) if isinstance(telemetry_window, (list, tuple)) else 0
    if n == 0:
        return {
            'diagnosis': 'no telemetry available',
            'adjusted_setpoints': {'tank1': t1_sp, 'tank2': t2_sp},
            'anomaly_flags': {'tank1': False, 'tank2': False},
        }

    def series(tank, key):
        out = []
        for step in telemetry_window:
            val = 0.0
            if isinstance(step, dict):
                d = step.get(tank)
                if isinstance(d, dict):
                    x = d.get(key, 0.0)
                    if isinstance(x, bool):
                        x = 0.0
                    elif isinstance(x, (int, float)):
                        val = float(x)
            out.append(val)
        return out

    lvl1 = series('tank1', 'level')
    lvl2 = series('tank2', 'level')
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
        return (s[m // 2 - 1] + s[m // 2]) / 2.0

    def mean_abs(xs):
        if not xs:
            return 0.0
        total = 0.0
        for x in xs:
            total += abs(x)
        return total / float(len(xs))

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
        frac = pos - lo
        return s[lo] * (1.0 - frac) + s[hi] * frac

    def tail(xs, kk):
        if kk <= 0:
            return []
        if len(xs) <= kk:
            return xs
        return xs[len(xs) - kk:]

    def rolling_median(xs, win):
        out = []
        m = len(xs)
        for i in range(m):
            lo = i - win + 1
            if lo < 0:
                lo = 0
            out.append(median(xs[lo:i + 1]))
        return out

    def frac_above(xs, thr, win):
        seg = tail(xs, win)
        m = len(seg)
        if m <= 0:
            return 0.0
        cnt = 0
        for x in seg:
            if x > thr:
                cnt += 1
        return cnt / float(m)

    def normalized_effort(effs, lvls, nom):
        scale = abs(nom)
        if scale <= 0.0:
            scale = 1.0
        floor_h = 0.3 * scale
        smooth = rolling_median(lvls, 3)
        out = []
        for i in range(len(effs)):
            hh = smooth[i]
            if hh < floor_h:
                hh = floor_h
            out.append(effs[i] * scale / hh)
        return out

    v1 = normalized_effort(eff1, lvl1, nom1)
    v2 = normalized_effort(eff2, lvl2, nom2)

    rm1 = rolling_median(v1, 5)
    rm2 = rolling_median(v2, 5)
    e_n = max(3, min(8, n // 3))
    if e_n > n:
        e_n = n
    ref1 = min(quantile(rm1, 0.20), quantile(v1[:e_n], 0.25))
    ref2 = min(quantile(rm2, 0.20), quantile(v2[:e_n], 0.25))

    k = min(8, n)
    h = max(3, min(5, k))
    wlong = min(16, n)

    te1 = median(tail(v1, k))
    te2 = median(tail(v2, k))
    ae1 = mean_abs(tail(err1, k))
    ae2 = mean_abs(tail(err2, k))

    thr1 = max(0.40, 0.30 * ref1)
    thr2 = max(0.32, 0.28 * ref2)

    ex1 = te1 - ref1
    ex2 = te2 - ref2

    sus1 = frac_above(v1, ref1 + thr1, wlong) >= 0.6
    sus2 = frac_above(v2, ref2 + thr2, wlong) >= 0.6

    raw1 = bool((ex1 > thr1 and ae1 > 0.05) or (ex1 > 1.6 * thr1) or sus1)
    raw2 = bool((ex2 > thr2 and ae2 > 0.05) or (ex2 > 1.6 * thr2) or sus2)

    rec1 = bool((median(tail(v1, h)) <= ref1 + 0.45 * thr1) and (mean_abs(tail(err1, h)) <= 0.14))
    rec2 = bool((median(tail(v2, h)) <= ref2 + 0.40 * thr2) and (mean_abs(tail(err2, h)) <= 0.14))

    tank1_anom = bool(raw1 and not rec1)

    r1 = ex1 / max(ref1, 1e-6)
    r2 = ex2 / max(ref2, 1e-6)
    rt2 = thr2 / max(ref2, 1e-6)
    upstream1 = bool(raw1 or ex1 > 0.6 * thr1)
    r1_pos = r1 if r1 > 0.0 else 0.0
    cascade_bound = 0.50 * r1_pos + rt2
    cascade = bool(upstream1 and raw2 and (r2 <= cascade_bound) and (r2 <= 2.5 * rt2))
    tank2_anom = bool(raw2 and not rec2 and not cascade)

    LOWER_STEP = 0.3
    RESTORE_STEP = 0.8
    MAX_DEPRESS = 0.8

    if tank1_anom:
        cand1 = max(nom1 - MAX_DEPRESS, t1_sp - LOWER_STEP)
        if cand1 > t1_sp:
            cand1 = t1_sp
        new1 = cand1
        diag1 = 'tank1 anomaly suspected (setpoint-invariant effort elevation above healthy baseline)'
    elif (ex1 < 0.6 * thr1) and (ae1 < 0.14) and (t1_sp < nom1):
        new1 = min(nom1, t1_sp + RESTORE_STEP)
        diag1 = 'tank1 stable, restoring toward nominal'
    else:
        new1 = t1_sp
        diag1 = 'tank1 nominal'

    if tank2_anom:
        cand2 = max(nom2 - MAX_DEPRESS, t2_sp - LOWER_STEP)
        if cand2 > t2_sp:
            cand2 = t2_sp
        new2 = cand2
        diag2 = 'tank2 anomaly suspected (independent, residual exceeds upstream coupling bound)'
    elif cascade:
        new2 = t2_sp
        diag2 = 'tank2 perturbation attributed to upstream tank1 fault (bounded by coupling residual)'
    elif (ex2 < 0.6 * thr2) and (ae2 < 0.14) and (t2_sp < nom2):
        new2 = min(nom2, t2_sp + RESTORE_STEP)
        diag2 = 'tank2 stable, restoring toward nominal'
    else:
        new2 = t2_sp
        diag2 = 'tank2 nominal'

    return {
        'diagnosis': diag1 + '; ' + diag2,
        'adjusted_setpoints': {'tank1': new1, 'tank2': new2},
        'anomaly_flags': {'tank1': tank1_anom, 'tank2': tank2_anom},
    }
