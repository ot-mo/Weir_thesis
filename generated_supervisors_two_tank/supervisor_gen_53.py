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
        fr = pos - lo
        return s[lo] * (1.0 - fr) + s[hi] * fr

    def tail(xs, kk):
        if kk <= 0:
            return []
        if len(xs) <= kk:
            return xs
        return xs[len(xs) - kk:]

    def rolling_medians(xs, hh):
        out = []
        m = len(xs)
        for i in range(m):
            lo = i - hh + 1
            if lo < 0:
                lo = 0
            out.append(median(xs[lo:i + 1]))
        return out

    k = min(6, n)
    w = min(10, n)
    wlong = min(20, n)
    h = max(3, min(5, k))
    early_n = n // 3
    if early_n < 3:
        early_n = 3
    if early_n > 8:
        early_n = 8
    if early_n > n:
        early_n = n

    def analyze(effs, errs, sp, nom):
        q_early = quantile(effs[:early_n], 0.15)
        rmeds = rolling_medians(effs, h)
        q_roll = quantile(rmeds, 0.15)
        ref = q_early if q_early < q_roll else q_roll
        if ref < 0.05:
            ref = 0.05

        sp_eff = sp if sp > 0.05 else nom
        scale = nom / sp_eff
        if scale < 1.0:
            scale = 1.0

        te = median(tail(effs, k))
        te_n = te * scale
        ae = mean_abs(tail(errs, k))

        thr_mild = ref + max(0.35, 0.30 * ref)
        thr_strong = ref + max(0.80, 0.65 * ref)

        mild = te_n > thr_mild
        strong = te_n > thr_strong

        seg_w = tail(effs, w)
        mw = len(seg_w)
        cntw = 0
        for v in seg_w:
            if v * scale > thr_mild:
                cntw += 1
        frac_w = cntw / float(mw) if mw else 0.0
        sus = frac_w >= 0.6

        seg_l = tail(effs, wlong)
        ml = len(seg_l)
        cntl = 0
        for v in seg_l:
            if v * scale > thr_mild:
                cntl += 1
        frac_l = cntl / float(ml) if ml else 0.0
        persist = frac_l >= 0.55

        det = bool(strong or mild or sus)

        rec_low = (median(tail(effs, h)) * scale <= ref + max(0.25, 0.22 * ref)) and (mean_abs(tail(errs, h)) <= 0.12)
        rec_low = bool(rec_low)

        excess = te_n - ref
        return {
            'ref': ref,
            'te': te,
            'te_n': te_n,
            'excess': excess,
            'ae': ae,
            'det': det,
            'strong': bool(strong),
            'persist': bool(persist),
            'rec_low': rec_low,
        }

    a1 = analyze(eff1, err1, t1_sp, nom1)
    a2 = analyze(eff2, err2, t2_sp, nom2)

    upstream = a1['excess']
    if upstream < 0.0:
        upstream = 0.0
    t1_active = a1['det']

    CG = 0.5
    margin2 = max(0.30, 0.25 * a2['ref'])
    needed2 = CG * upstream + margin2
    t2_own = a2['det']
    if t1_active:
        t2_raw = bool(t2_own and (a2['excess'] > needed2 or a2['strong']))
    else:
        t2_raw = bool(t2_own)
    cascade = bool(t1_active and t2_own and (not t2_raw))

    def decide(raw_det, rec_low, sp, nom, at_nominal):
        dep = nom * 0.90
        if at_nominal:
            if raw_det:
                return True, dep
            return False, nom
        if raw_det or (not rec_low):
            return True, sp
        return False, nom

    t1_at_nom = t1_sp >= nom1 * 0.995
    t2_at_nom = t2_sp >= nom2 * 0.995

    anom1, new1 = decide(a1['det'], a1['rec_low'], t1_sp, nom1, t1_at_nom)
    anom2, new2 = decide(t2_raw, a2['rec_low'], t2_sp, nom2, t2_at_nom)

    if anom1:
        diag1 = 'tank1 anomaly suspected'
    else:
        diag1 = 'tank1 nominal'
    if anom2:
        diag2 = 'tank2 anomaly suspected (independent of upstream)'
    elif cascade:
        diag2 = 'tank2 elevated but attributed to tank1 cascade'
    else:
        diag2 = 'tank2 nominal'

    return {
        'diagnosis': diag1 + '; ' + diag2,
        'adjusted_setpoints': {'tank1': new1, 'tank2': new2},
        'anomaly_flags': {'tank1': anom1, 'tank2': anom2},
    }