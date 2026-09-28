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

    win = telemetry_window if isinstance(telemetry_window, (list, tuple)) else []
    n = len(win)
    if n == 0:
        return {
            'diagnosis': 'no telemetry available',
            'adjusted_setpoints': {'tank1': t1_sp, 'tank2': t2_sp},
            'anomaly_flags': {'tank1': False, 'tank2': False},
        }

    def series(tank, key):
        out = []
        for step in win:
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
    lvl1 = series('tank1', 'level')
    lvl2 = series('tank2', 'level')

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
            return list(xs)
        return xs[len(xs) - kk:]

    def rolling_median(xs, w):
        out = []
        m = len(xs)
        for i in range(m):
            lo = i - w + 1
            if lo < 0:
                lo = 0
            out.append(median(xs[lo:i + 1]))
        return out

    def frac_gt(xs, thr):
        if not xs:
            return 0.0
        c = 0
        for v in xs:
            if v > thr:
                c += 1
        return c / float(len(xs))

    def invariant_eff(effs, lvls, nom):
        if abs(nom) > 1e-6:
            fl = 0.5 * abs(nom)
        else:
            fl = 1e-6
        out = []
        for i in range(len(effs)):
            L = lvls[i]
            if not (L == L):
                L = fl
            if L < fl:
                L = fl
            if abs(nom) > 1e-6:
                out.append(effs[i] * nom / L)
            else:
                out.append(effs[i])
        return out

    x1 = invariant_eff(eff1, lvl1, nom1)
    x2 = invariant_eff(eff2, lvl2, nom2)

    ws = min(5, n)
    ref1 = quantile(rolling_median(x1, ws), 0.15)
    ref2 = quantile(rolling_median(x2, ws), 0.15)

    w = min(10, n)
    wlong = min(16, n)
    K = min(6, n)

    te1 = median(tail(x1, K))
    te2 = median(tail(x2, K))
    ae1 = mean_abs(tail(err1, K))
    ae2 = mean_abs(tail(err2, K))
    me1 = median(tail(eff1, K))
    me2 = median(tail(eff2, K))

    dev1 = te1 - ref1
    dev2 = te2 - ref2

    raw1 = bool(
        (dev1 > 0.45 and ae1 > 0.08)
        or (dev1 > 0.85)
        or (te1 > 2.50)
        or (frac_gt(tail(x1, wlong), 2.20) >= 0.80)
        or (frac_gt(tail(x1, w), ref1 + 0.45) >= 0.60)
    )
    raw2 = bool(
        (dev2 > 0.35 and ae2 > 0.08)
        or (dev2 > 0.75)
        or (te2 > 2.00)
        or (frac_gt(tail(x2, wlong), 1.95) >= 0.80)
        or (frac_gt(tail(x2, w), ref2 + 0.35) >= 0.60)
    )

    rec1 = bool((te1 <= ref1 + 0.45) and (me1 <= 2.05) and (ae1 <= 0.14))
    rec2 = bool((te2 <= ref2 + 0.35) and (me2 <= 1.80) and (ae2 <= 0.14))

    depressed1 = t1_sp < nom1 - 0.02
    depressed2 = t2_sp < nom2 - 0.02

    up_active1 = bool(raw1 or depressed1)
    up1 = te1 - ref1
    if up1 < 0.0:
        up1 = 0.0
    pers2 = frac_gt(tail(x2, wlong), ref2 + 0.35) >= 0.75
    over_coupling = dev2 > 0.80 * up1 + 0.15
    t2_indep = bool(pers2 and (over_coupling or (te2 > 2.45)))
    cascade = bool(up_active1 and raw2 and (not t2_indep))

    LOWER_STEP = 0.3
    MAX_DEPRESS = 1.0

    if raw1:
        cand = max(nom1 - MAX_DEPRESS, t1_sp - LOWER_STEP)
        if cand > t1_sp:
            cand = t1_sp
        new1 = cand
        flag1 = True
        diag1 = 'tank1 anomaly: invariant effort above own baseline'
    elif depressed1:
        if rec1:
            new1 = nom1
            diag1 = 'tank1 recovering: verification pulse at nominal'
        else:
            new1 = t1_sp
            diag1 = 'tank1 anomaly latched: holding depressed setpoint'
        flag1 = True
    else:
        new1 = t1_sp
        flag1 = False
        diag1 = 'tank1 nominal'

    if raw2 and (not cascade):
        cand = max(nom2 - MAX_DEPRESS, t2_sp - LOWER_STEP)
        if cand > t2_sp:
            cand = t2_sp
        new2 = cand
        flag2 = True
        diag2 = 'tank2 anomaly: independent of upstream coupling'
    elif cascade:
        if depressed2:
            new2 = nom2
        else:
            new2 = t2_sp
        flag2 = False
        diag2 = 'tank2 perturbation attributed to upstream tank1 (cascade, not flagged)'
    elif depressed2:
        if rec2:
            new2 = nom2
            diag2 = 'tank2 recovering: verification pulse at nominal'
        else:
            new2 = t2_sp
            diag2 = 'tank2 anomaly latched: holding depressed setpoint'
        flag2 = True
    else:
        new2 = t2_sp
        flag2 = False
        diag2 = 'tank2 nominal'

    return {
        'diagnosis': diag1 + '; ' + diag2,
        'adjusted_setpoints': {'tank1': new1, 'tank2': new2},
        'anomaly_flags': {'tank1': bool(flag1), 'tank2': bool(flag2)},
    }
