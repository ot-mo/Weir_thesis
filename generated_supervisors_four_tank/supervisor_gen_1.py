def supervise(telemetry_window, active_setpoints, nominal_targets):
    def _median(vals):
        if not vals:
            return 0.0
        sv = sorted(vals)
        m = len(sv)
        if m % 2 == 1:
            return sv[m // 2]
        return (sv[m // 2 - 1] + sv[m // 2]) / 2.0

    def _mean(vals):
        return sum(vals) / len(vals) if vals else 0.0

    n = len(telemetry_window)
    sp1 = active_setpoints['tank1']
    sp2 = active_setpoints['tank2']
    nom1 = nominal_targets['tank1']
    nom2 = nominal_targets['tank2']

    if n < 3:
        return {'diagnosis': 'insufficient telemetry window',
                'adjusted_setpoints': {'tank1': sp1, 'tank2': sp2},
                'anomaly_flags': {'tank1': False, 'tank2': False}}

    def _series(tank, key):
        return [step[tank][key] for step in telemetry_window]

    eff1 = _series('tank1', 'pump_effort')
    eff2 = _series('tank2', 'pump_effort')
    err1 = _series('tank1', 'error')
    err2 = _series('tank2', 'error')
    lvl1 = _series('tank1', 'level')
    lvl2 = _series('tank2', 'level')

    w = max(3, n // 3)

    def _features(eff, err, sp, nom):
        early_eff = _median(eff[:w])
        late_eff = _median(eff[-w:])
        early_err = _mean([abs(e) for e in err[:w]])
        late_abs = _mean([abs(e) for e in err[-w:]])
        late_signed = _mean(err[-w:])
        scale = max(abs(nom), abs(sp), 0.05)
        return {'eff_ratio': late_eff / max(early_eff, 0.5),
                'err_ratio': late_abs / max(early_err, 0.005),
                'bias': abs(late_signed) / (late_abs + 1e-9),
                'err_norm': late_abs / scale}

    f1 = _features(eff1, err1, sp1, nom1)
    f2 = _features(eff2, err2, sp2, nom2)

    def _load(eff, lvl, sp):
        heads = [math.sqrt(v) for v in lvl[-w:] if v > 1e-6]
        mh = _mean(heads) if heads else 1e-6
        return _median(eff[-w:]) / (mh + 1e-6) / math.sqrt(max(sp, 0.02))

    l1 = _load(eff1, lvl1, sp1)
    l2 = _load(eff2, lvl2, sp2)
    load_ratio = l1 / l2 if l2 > 1e-9 else 1.0
    compare_ok = abs(sp1 - sp2) < 0.25 * max(abs(nom1), abs(nom2), 0.05)
    cross1 = compare_ok and load_ratio > 1.4
    cross2 = compare_ok and load_ratio < 0.71

    def _growth(f):
        if f['eff_ratio'] > 1.4 and f['err_ratio'] > 1.25:
            return True
        if f['eff_ratio'] > 1.6 and f['err_norm'] > 0.05:
            return True
        if f['bias'] > 0.72 and f['err_norm'] > 0.12 and f['eff_ratio'] > 1.05:
            return True
        return False

    g1 = _growth(f1)
    g2 = _growth(f2)

    if cross1 and not cross2:
        a1 = True
        a2 = g2 and f2['eff_ratio'] > 1.3 and f2['err_norm'] > 0.1
    elif cross2 and not cross1:
        a2 = True
        a1 = g1 and f1['eff_ratio'] > 1.3 and f1['err_norm'] > 0.1
    else:
        a1 = g1 or cross1
        a2 = g2 or cross2

    cross_quiet = abs(load_ratio - 1.0) < 0.2

    def _calm(f):
        return cross_quiet and f['bias'] < 0.4 and f['err_norm'] < 0.06 and f['eff_ratio'] < 1.15

    c1 = (not a1) and _calm(f1)
    c2 = (not a2) and _calm(f2)

    LOWER_STEP = 0.02
    RESTORE_FRAC = 0.4

    def _next_sp(sp, nom, anomaly, calm):
        if anomaly:
            return max(0.05, sp - LOWER_STEP)
        if calm and abs(sp - nom) > 1e-9:
            tgt = sp + (nom - sp) * RESTORE_FRAC
            if (sp < nom and tgt >= nom - 0.002) or (sp > nom and tgt <= nom + 0.002):
                tgt = nom
            return tgt
        return sp

    new1 = _next_sp(sp1, nom1, a1, c1)
    new2 = _next_sp(sp2, nom2, a2, c2)

    return {'diagnosis': 'tank1 anomaly=%s; tank2 anomaly=%s' % (a1, a2),
            'adjusted_setpoints': {'tank1': new1, 'tank2': new2},
            'anomaly_flags': {'tank1': a1, 'tank2': a2}}