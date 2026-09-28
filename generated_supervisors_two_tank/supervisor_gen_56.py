def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---------------- helpers ----------------
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

    def fnum(x, d=0.0):
        try:
            if isinstance(x, bool):
                return float(d)
            if isinstance(x, (int, float)):
                return float(x)
            return float(d)
        except (TypeError, ValueError):
            return float(d)

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
        t = 0.0
        for x in xs:
            t += abs(x)
        return t / float(len(xs))

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

    def frac_above(xs, thr, win):
        seg = tail(xs, win)
        m = len(seg)
        if m <= 0:
            return 0.0
        cnt = 0
        for e in seg:
            if e > thr:
                cnt += 1
        return cnt / float(m)

    def frac_cond(effs, errs, thr_e, thr_r, win):
        se = tail(effs, win)
        sr = tail(errs, win)
        m = len(se)
        if m <= 0:
            return 0.0
        cnt = 0
        for i in range(m):
            if se[i] > thr_e and abs(sr[i]) > thr_r:
                cnt += 1
        return cnt / float(m)

    def rolling_median_ref(xs, win, q):
        m = len(xs)
        if m <= 0:
            return 0.0
        if win <= 0:
            win = 1
        ww = win if win <= m else m
        vals = []
        for i in range(0, m - ww + 1):
            vals.append(median(xs[i:i + ww]))
        if not vals:
            return 0.0
        return quantile(vals, q)

    # ---------------- inputs ----------------
    t1_sp = _num(active_setpoints, 'tank1', 0.0)
    t2_sp = _num(active_setpoints, 'tank2', 0.0)
    nom1 = _num(nominal_targets, 'tank1', t1_sp)
    nom2 = _num(nominal_targets, 'tank2', t2_sp)

    if nom1 < 0.05:
        nom1 = max(t1_sp, 1.0)
    if nom2 < 0.05:
        nom2 = max(t2_sp, 1.0)

    n = len(telemetry_window) if isinstance(telemetry_window, (list, tuple)) else 0
    if n == 0:
        return {
            'diagnosis': 'no telemetry available',
            'adjusted_setpoints': {'tank1': t1_sp, 'tank2': t2_sp},
            'anomaly_flags': {'tank1': False, 'tank2': False},
        }

    lev1 = []
    lev2 = []
    eff1 = []
    eff2 = []
    err1 = []
    err2 = []
    for step in telemetry_window:
        l1 = 0.0
        e1 = 0.0
        r1 = 0.0
        l2 = 0.0
        e2 = 0.0
        r2 = 0.0
        if isinstance(step, dict):
            d1 = step.get('tank1')
            if isinstance(d1, dict):
                l1 = fnum(d1.get('level', 0.0))
                e1 = fnum(d1.get('pump_effort', 0.0))
                r1 = fnum(d1.get('error', 0.0))
            d2 = step.get('tank2')
            if isinstance(d2, dict):
                l2 = fnum(d2.get('level', 0.0))
                e2 = fnum(d2.get('pump_effort', 0.0))
                r2 = fnum(d2.get('error', 0.0))
        lev1.append(l1)
        eff1.append(e1)
        err1.append(r1)
        lev2.append(l2)
        eff2.append(e2)
        err2.append(r2)

    # Normalise pump effort by nominal/active_setpoint so the statistic is
    # invariant to the supervisor's own setpoint moves (breaks the
    # detect -> depress -> clear -> restore oscillation).  Both DETECTION and
    # CLEARANCE use this same normalised signal, so a still-active fault keeps
    # a raised statistic at any setpoint.
    r1_sp = nom1 / max(abs(t1_sp), 0.05)
    if r1_sp < 0.5:
        r1_sp = 0.5
    if r1_sp > 2.5:
        r1_sp = 2.5
    r2_sp = nom2 / max(abs(t2_sp), 0.05)
    if r2_sp < 0.5:
        r2_sp = 0.5
    if r2_sp > 2.5:
        r2_sp = 2.5

    ne1 = []
    for i in range(n):
        ne1.append(eff1[i] * r1_sp)
    ne2 = []
    for i in range(n):
        ne2.append(eff2[i] * r2_sp)

    # ---------------- constants ----------------
    W_ROLL = 5
    Q_REF = 0.15
    L_REF = 0.20
    K_REC = 8
    H = max(3, min(5, n))
    W_SUST = min(12, n)
    W_LONG = min(16, n)

    E_SPIKE = 0.90
    E_DEV_FLOOR = 0.30
    E_DEV_REL = 0.40
    E_ERR = 0.10
    E_PERS = 0.20
    E_REC_FLOOR = 0.18
    E_REC_REL = 0.35

    LOWER_STEP = 0.3
    RESTORE_STEP = 0.8
    MAX_DEPRESS = 1.0

    # ---------------- baselines (rolling-median low quantile) ----------------
    ref1 = rolling_median_ref(ne1, W_ROLL, Q_REF)
    ref2 = rolling_median_ref(ne2, W_ROLL, Q_REF)

    if ref1 <= 0.0:
        ref1 = max(mean(ne1) * Q_REF, 1e-6)
    if ref2 <= 0.0:
        ref2 = max(mean(ne2) * Q_REF, 1e-6)

    tmed1 = median(tail(ne1, K_REC))
    tmed2 = median(tail(ne2, K_REC))
    errm1 = mean_abs(tail(err1, K_REC))
    errm2 = mean_abs(tail(err2, K_REC))

    dev1 = tmed1 - ref1
    dev2 = tmed2 - ref2
    ex1 = dev1 if dev1 > 0.0 else 0.0
    ex2 = dev2 if dev2 > 0.0 else 0.0

    # ---------------- per-tank raw detection ----------------
    def detect(tmed, ref, ex, errm, ne, err):
        spike = (ex > E_SPIKE) and (errm > 0.5 * E_ERR)
        dev_anom = (ex > max(E_DEV_FLOOR, E_DEV_REL * ref)) and (errm > E_ERR)
        sthr = ref + max(E_DEV_FLOOR, 0.5 * E_DEV_REL * ref)
        sust = frac_above(ne, sthr, W_SUST) >= 0.6
        fcond = frac_cond(ne, err, sthr, E_ERR, W_LONG) > 0.5
        raw = bool(spike or dev_anom or sust or fcond)
        return raw

    raw1 = detect(tmed1, ref1, ex1, errm1, ne1, err1)
    raw2 = detect(tmed2, ref2, ex2, errm2, ne2, err2)

    # ---------------- per-call latch proxy (setpoint below nominal) ----------------
    dep1 = t1_sp < nom1 - 0.05
    dep2 = t2_sp < nom2 - 0.05

    if dep1:
        rm1 = max(E_REC_FLOOR, 0.80 * ref1)
    else:
        rm1 = max(E_REC_FLOOR, E_REC_REL * ref1)
    if dep2:
        rm2 = max(E_REC_FLOOR, 0.80 * ref2)
    else:
        rm2 = max(E_REC_FLOOR, E_REC_REL * ref2)

    rec1 = (ex1 < rm1) and (errm1 <= E_ERR)
    rec2 = (ex2 < rm2) and (errm2 <= E_ERR)

    tank1_anom = bool(raw1 and not rec1)

    # ---------------- cascade coupling (upstream -> downstream residual) ----------------
    coupling_gain = 0.90
    margin2 = 0.10 * ref2
    if margin2 < 0.03:
        margin2 = 0.03
    coupled_excess2 = coupling_gain * ex1
    residual2 = ex2 - coupled_excess2

    persist2 = (
        (frac_above(ne2, ref2 + E_PERS, W_LONG) >= 0.6) or
        (frac_above(ne2, ref2 + 2.0 * E_PERS, W_SUST) >= 0.4)
    )

    independent2 = (raw2 and (residual2 > margin2)) or (persist2 and (ex2 > E_PERS))

    if tank1_anom:
        tank2_anom = bool(raw2 and independent2)
    else:
        tank2_anom = bool(raw2)

    # ---------------- setpoint coordination ----------------
    floor1 = nom1 - MAX_DEPRESS
    if floor1 < 0.2:
        floor1 = 0.2
    floor2 = nom2 - MAX_DEPRESS
    if floor2 < 0.2:
        floor2 = 0.2

    if tank1_anom:
        cand1 = max(floor1, t1_sp - LOWER_STEP)
        if cand1 > t1_sp:
            cand1 = t1_sp
        new1 = cand1
        diag1 = 'tank1 anomaly suspected (effort shift above rolling reference)'
    elif rec1 and (t1_sp < nom1 - 1e-9):
        new1 = min(nom1, t1_sp + RESTORE_STEP)
        diag1 = 'tank1 clear, restoring toward nominal'
    else:
        new1 = t1_sp
        diag1 = 'tank1 nominal'

    if tank2_anom:
        cand2 = max(floor2, t2_sp - LOWER_STEP)
        if cand2 > t2_sp:
            cand2 = t2_sp
        new2 = cand2
        diag2 = 'tank2 anomaly suspected (independent of upstream coupling)'
    elif rec2 and (t2_sp < nom2 - 1e-9):
        new2 = min(nom2, t2_sp + RESTORE_STEP)
        diag2 = 'tank2 clear, restoring toward nominal'
    else:
        new2 = t2_sp
        if tank1_anom and raw2:
            diag2 = 'tank2 elevation attributed to upstream cascade (not flagged)'
        else:
            diag2 = 'tank2 nominal'

    return {
        'diagnosis': diag1 + '; ' + diag2,
        'adjusted_setpoints': {'tank1': new1, 'tank2': new2},
        'anomaly_flags': {'tank1': tank1_anom, 'tank2': tank2_anom},
    }