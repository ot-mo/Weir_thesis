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
    if nom1 <= 0.0:
        nom1 = t1_sp if t1_sp > 0.0 else 1.0
    if nom2 <= 0.0:
        nom2 = t2_sp if t2_sp > 0.0 else 1.0

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
    lvl1 = series('tank1', 'level')
    lvl2 = series('tank2', 'level')
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

    def mean_abs(xs):
        if not xs:
            return 0.0
        tot = 0.0
        for x in xs:
            tot += abs(x)
        return tot / float(len(xs))

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
        f = pos - lo
        return s[lo] * (1.0 - f) + s[hi] * f

    def tail(xs, kk):
        if kk <= 0:
            return []
        if len(xs) <= kk:
            return xs
        return xs[len(xs) - kk:]

    def rolling_median(xs, m):
        out = []
        for i in range(len(xs)):
            lo = i - m + 1
            if lo < 0:
                lo = 0
            out.append(median(xs[lo:i + 1]))
        return out

    def norm_effort(effs, lvls, nom):
        base = median(lvls) if lvls else 0.0
        if base < 0.05 * nom:
            return list(effs)
        sm = rolling_median(lvls, 3)
        floor = 0.35 * nom
        out = []
        for i in range(len(effs)):
            L = sm[i] if i < len(sm) else base
            if L < floor:
                L = floor
            out.append(effs[i] * nom / L)
        return out

    nr1 = norm_effort(eff1, lvl1, nom1)
    nr2 = norm_effort(eff2, lvl2, nom2)

    k = min(8, n)
    wl = min(20, n)
    h = max(3, min(5, k))

    def reference(nr):
        m = len(nr)
        if m == 0:
            return 0.0
        rm = rolling_median(nr, 3)
        kk = m // 3
        if kk < 3:
            kk = 3
        if kk > m:
            kk = m
        return min(quantile(rm[:kk], 0.20), quantile(rm, 0.20))

    def tank_stats(nr, err, nom, rel, absm, capfrac):
        ref = reference(nr)
        margin = max(absm, rel * ref)
        err_tol = max(0.15, 0.04 * nom)
        err_gate = max(0.08, 0.02 * nom)
        te = median(tail(nr, k))
        ae = mean_abs(tail(err, k))
        dev = te - ref
        dev_anom = (dev > margin and ae > err_gate) or (dev > 1.9 * margin)
        seg = tail(nr, wl)
        thr = ref + 0.60 * margin
        cnt = 0
        for v in seg:
            if v > thr:
                cnt += 1
        frac = (cnt / float(len(seg))) if seg else 0.0
        pers = frac >= 0.65
        cap = capfrac * nom
        abs_anom = te > cap
        rte = median(tail(nr, h))
        rae = mean_abs(tail(err, h))
        rec = (rte <= ref + 0.55 * margin) and (rte <= 1.10 * cap) and (rae <= err_tol)
        healthy = (dev < 0.5 * margin) and (ae <= err_tol)
        return {
            'ref': ref, 'te': te, 'ae': ae, 'dev': dev, 'margin': margin,
            'dev_anom': dev_anom, 'pers': pers, 'frac': frac, 'cap': cap,
            'abs_anom': abs_anom, 'rec': rec, 'healthy': healthy,
        }

    s1 = tank_stats(nr1, err1, nom1, 0.16, 0.45, 0.50)
    s2 = tank_stats(nr2, err2, nom2, 0.14, 0.38, 0.40)

    raw1 = bool(s1['dev_anom'] or s1['pers'] or s1['abs_anom'])
    raw2 = bool(s2['dev_anom'] or s2['pers'] or s2['abs_anom'])

    tank1_anom = bool(raw1 and (not s1['rec']))

    excess1 = max(0.0, s1['dev'])
    excess2 = max(0.0, s2['dev'])
    strong2 = bool(
        s2['abs_anom'] or
        (s2['pers'] and (excess2 > max(0.25, 0.10 * s2['ref']) + 0.5 * excess1))
    )
    up_active = bool(raw1 or tank1_anom)
    cascade2 = bool(up_active and raw2 and (not strong2))
    tank2_anom = bool(raw2 and (not s2['rec']) and (not cascade2))

    LOWER_STEP = 0.35
    RESTORE_STEP = 1.0
    MAX_DEPRESS = 1.0

    if tank1_anom:
        cand1 = max(nom1 - MAX_DEPRESS, t1_sp - LOWER_STEP)
        if cand1 > t1_sp:
            cand1 = t1_sp
        new1 = cand1
        diag1 = 'tank1 anomaly: level-normalized effort above its own healthy baseline'
    elif s1['healthy'] and t1_sp < nom1:
        new1 = min(nom1, t1_sp + RESTORE_STEP)
        diag1 = 'tank1 recovered, restoring toward nominal'
    else:
        new1 = t1_sp
        diag1 = 'tank1 nominal'

    if tank2_anom:
        cand2 = max(nom2 - MAX_DEPRESS, t2_sp - LOWER_STEP)
        if cand2 > t2_sp:
            cand2 = t2_sp
        new2 = cand2
        diag2 = 'tank2 anomaly independent of upstream cascade coupling'
    elif cascade2:
        new2 = t2_sp
        diag2 = 'tank2 perturbation attributed to upstream tank1 coupling (not flagged)'
    elif s2['healthy'] and t2_sp < nom2:
        new2 = min(nom2, t2_sp + RESTORE_STEP)
        diag2 = 'tank2 recovered, restoring toward nominal'
    else:
        new2 = t2_sp
        diag2 = 'tank2 nominal'

    return {
        'diagnosis': diag1 + '; ' + diag2,
        'adjusted_setpoints': {'tank1': new1, 'tank2': new2},
        'anomaly_flags': {'tank1': tank1_anom, 'tank2': tank2_anom},
    }