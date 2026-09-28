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
                        val = 0.0
                    elif isinstance(x, (int, float)):
                        val = float(x)
            out.append(val)
        return out

    eff1 = series('tank1', 'pump_effort')
    eff2 = series('tank2', 'pump_effort')
    err1 = series('tank1', 'error')
    err2 = series('tank2', 'error')

    def mean(xs):
        if not xs:
            return 0.0
        return sum(xs) / float(len(xs))

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
        frac = pos - lo
        return s[lo] * (1.0 - frac) + s[hi] * frac

    def tail(xs, cnt):
        if cnt <= 0:
            return []
        if len(xs) <= cnt:
            return xs
        return xs[len(xs) - cnt:]

    def frac_above(xs, thr, win):
        seg = tail(xs, win)
        m = len(seg)
        if m <= 0:
            return 0.0
        c = 0
        for x in seg:
            if x > thr:
                c += 1
        return c / float(m)

    def assess(eff, err, sp, nom):
        m = len(eff)
        kk = max(1, min(4, m))
        w = max(1, min(8, m))
        wl = max(1, min(20, m))
        third = max(1, m // 4)

        q_early = quantile(eff[:third], 0.20)
        q_full = quantile(eff, 0.20)
        ref = q_early if q_early < q_full else q_full

        sf = 1.0
        if nom > 1e-6:
            sf = sp / nom
            if sf < 0.6:
                sf = 0.6
            elif sf > 1.0:
                sf = 1.0
        ref_eff = ref * sf

        te = median(tail(eff, kk))
        tr = mean(tail(eff, max(1, min(3, m))))
        dev = te - ref_eff
        devr = tr - ref_eff
        peak = dev if dev > devr else devr
        ae = mean_abs(tail(err, kk))

        m_mild = max(0.45, 0.30 * ref_eff)
        m_strong = max(0.85, 0.45 * ref_eff)
        m_sust = max(0.40, 0.28 * ref_eff)
        m_pers = max(0.70, 0.40 * ref_eff)

        strong = peak > m_strong
        mild = (dev > m_mild) and (ae > 0.12)
        sust = frac_above(eff, ref_eff + m_sust, w) >= 0.75
        raw = bool(strong or mild or sust)

        pers = frac_above(eff, ref_eff + m_pers, wl) >= 0.70

        return {
            'ref': ref,
            'ref_eff': ref_eff,
            'dev': dev,
            'peak': peak,
            'ae': ae,
            'raw': raw,
            'pers': pers,
        }

    a1 = assess(eff1, err1, t1_sp, nom1)
    a2 = assess(eff2, err2, t2_sp, nom2)

    raw1 = a1['raw']
    raw2 = a2['raw']

    up_peak = a1['peak'] if a1['peak'] > 0.0 else 0.0
    couple_allow = 0.75 * up_peak + 0.25 * a2['ref_eff']
    independent2 = bool(a2['pers'] and (a2['peak'] > couple_allow))

    cascade = bool(raw1 and raw2 and (not independent2))
    tank1_anom = bool(raw1)
    tank2_anom = bool(raw2 and (not cascade))

    LOWER_STEP = 0.3
    RESTORE_STEP = 1.0
    MAX_DEPRESS = 1.0

    def adjust(anom, a, sp, nom):
        if anom:
            cand = max(nom - MAX_DEPRESS, sp - LOWER_STEP)
            if cand > sp:
                cand = sp
            return cand
        if sp < nom:
            settled = (a['dev'] < max(0.20, 0.15 * a['ref_eff'])) and (a['ae'] < 0.15)
            if settled:
                nv = sp + RESTORE_STEP
                if nv > nom:
                    nv = nom
                return nv
        return sp

    new1 = adjust(tank1_anom, a1, t1_sp, nom1)
    new2 = adjust(tank2_anom, a2, t2_sp, nom2)

    if tank1_anom:
        diag1 = 'tank1 anomaly: sustained effort above setpoint-scaled healthy baseline'
    elif new1 > t1_sp:
        diag1 = 'tank1 settled, restoring setpoint toward nominal'
    else:
        diag1 = 'tank1 nominal'

    if tank2_anom:
        diag2 = 'tank2 anomaly: persistent effort beyond upstream-coupling allowance'
    elif cascade:
        diag2 = 'tank2 perturbation attributed to upstream tank1 fault (cascade, not flagged)'
    elif new2 > t2_sp:
        diag2 = 'tank2 settled, restoring setpoint toward nominal'
    else:
        diag2 = 'tank2 nominal'

    return {
        'diagnosis': diag1 + '; ' + diag2,
        'adjusted_setpoints': {'tank1': new1, 'tank2': new2},
        'anomaly_flags': {'tank1': tank1_anom, 'tank2': tank2_anom},
    }