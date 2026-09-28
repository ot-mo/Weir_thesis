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
        frac = pos - lo
        return s[lo] * (1.0 - frac) + s[hi] * frac

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
        c = 0
        for v in seg:
            if v > thr:
                c += 1
        return c / float(m)

    # Healthy pump-effort baseline anchored to the earliest (pre-fault) part
    # of the window; the full-window low quantile is only a floor.
    early_len = max(3, min(n // 3, 12))
    ref1 = min(quantile(eff1[:early_len], 0.20), quantile(eff1, 0.20))
    ref2 = min(quantile(eff2[:early_len], 0.20), quantile(eff2, 0.20))

    k = max(3, min(6, n))
    wr = max(3, min(5, n))
    ws = max(3, min(12, n))
    wl = max(3, min(20, n))

    te1 = median(tail(eff1, k))
    te2 = median(tail(eff2, k))
    ae1 = mean_abs(tail(err1, k))
    ae2 = mean_abs(tail(err2, k))
    re1 = median(tail(eff1, wr))
    re2 = median(tail(eff2, wr))
    rae1 = mean_abs(tail(err1, wr))
    rae2 = mean_abs(tail(err2, wr))

    dev1 = te1 - ref1
    dev2 = te2 - ref2
    climb1 = te1 - quantile(eff1, 0.10)
    climb2 = te2 - quantile(eff2, 0.10)

    # ---- tank1 leak signature (all bars relative to tank1's own baseline) ----
    shift1 = (dev1 > max(0.40, 0.28 * ref1)) and (ae1 > 0.05)
    big1 = dev1 > max(0.80, 0.50 * ref1)
    sust1 = (frac_above(eff1, ref1 + max(0.35, 0.25 * ref1), ws) >= 0.6) and (dev1 > max(0.15, 0.10 * ref1))
    climb_anom1 = climb1 > max(1.10, 0.60 * ref1)
    raw1 = bool(shift1 or big1 or sust1 or climb_anom1)

    # ---- tank2 leak signature (tighter bars: smaller hydraulic scale) ----
    shift2 = (dev2 > max(0.35, 0.26 * ref2)) and (ae2 > 0.05)
    big2 = dev2 > max(0.70, 0.48 * ref2)
    sust2 = (frac_above(eff2, ref2 + max(0.30, 0.24 * ref2), ws) >= 0.6) and (dev2 > max(0.12, 0.10 * ref2))
    climb_anom2 = climb2 > max(1.00, 0.58 * ref2)
    raw2 = bool(shift2 or big2 or sust2 or climb_anom2)

    # A compensated upstream leak keeps tank1's level (and hence its gravity
    # outflow into tank2) fixed, so cascade coupling is TRANSIENT.  Downstream
    # effort that stays elevated across a long window is therefore an
    # independent tank2 fault, not coupling.
    persist2 = frac_above(eff2, ref2 + max(0.28, 0.22 * ref2), wl) >= 0.70
    upstream_active = bool(raw1)
    indep2 = bool(
        big2
        or climb_anom2
        or (dev2 > max(0.45, 0.34 * ref2))
        or (persist2 and dev2 > max(0.28, 0.20 * ref2))
    )
    cascade = bool(upstream_active and raw2 and (not indep2))

    LOWER_STEP = 0.3
    RESTORE_STEP = 0.9
    MAX_DEPRESS = 1.0
    EPS = 0.05

    dep1 = t1_sp < nom1 - EPS
    dep2 = t2_sp < nom2 - EPS

    # ---------------- tank1 flag + setpoint ----------------
    if dep1:
        # our own earlier depression: keep the flag latched and verify at nominal
        tank1_anom = True
        new1 = nom1
        diag1 = 'tank1 anomaly latched (verifying at nominal setpoint)'
    else:
        rec1 = (re1 <= ref1 + max(0.28, 0.18 * ref1)) and (rae1 <= 0.15)
        if raw1 and not rec1:
            tank1_anom = True
            cand = t1_sp - LOWER_STEP
            if cand < nom1 - MAX_DEPRESS:
                cand = nom1 - MAX_DEPRESS
            if cand > t1_sp:
                cand = t1_sp
            new1 = cand
            diag1 = 'tank1 anomaly suspected (effort sustained above healthy baseline)'
        else:
            tank1_anom = False
            if t1_sp < nom1:
                new1 = min(nom1, t1_sp + RESTORE_STEP)
                diag1 = 'tank1 clear, restoring toward nominal'
            else:
                new1 = t1_sp
                diag1 = 'tank1 nominal'

    # ---------------- tank2 flag + setpoint ----------------
    if dep2 and cascade:
        tank2_anom = False
        new2 = nom2
        diag2 = 'tank2 latch released: upstream cascade explains perturbation'
    elif dep2:
        tank2_anom = True
        new2 = nom2
        diag2 = 'tank2 anomaly latched (verifying at nominal setpoint)'
    elif cascade:
        tank2_anom = False
        if t2_sp < nom2:
            new2 = min(nom2, t2_sp + RESTORE_STEP)
        else:
            new2 = t2_sp
        diag2 = 'tank2 perturbation attributed to upstream tank1 cascade (not flagged)'
    else:
        rec2 = (re2 <= ref2 + max(0.26, 0.16 * ref2)) and (rae2 <= 0.15)
        if raw2 and not rec2:
            tank2_anom = True
            cand = t2_sp - LOWER_STEP
            if cand < nom2 - MAX_DEPRESS:
                cand = nom2 - MAX_DEPRESS
            if cand > t2_sp:
                cand = t2_sp
            new2 = cand
            diag2 = 'tank2 anomaly suspected (independent of upstream coupling)'
        else:
            tank2_anom = False
            if t2_sp < nom2:
                new2 = min(nom2, t2_sp + RESTORE_STEP)
                diag2 = 'tank2 clear, restoring toward nominal'
            else:
                new2 = t2_sp
                diag2 = 'tank2 nominal'

    return {
        'diagnosis': diag1 + '; ' + diag2,
        'adjusted_setpoints': {'tank1': new1, 'tank2': new2},
        'anomaly_flags': {'tank1': tank1_anom, 'tank2': tank2_anom},
    }
