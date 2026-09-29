def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    sp1_in = active_setpoints["tank1"]
    sp2_in = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    if n < 12:
        return {
            "diagnosis": "insufficient telemetry",
            "adjusted_setpoints": {"tank1": sp1_in, "tank2": sp2_in},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    def mean(vals):
        return sum(vals) / float(len(vals))

    def col(tank, field):
        return [step[tank][field] for step in telemetry_window]

    # ---- constants anchored on the measured fault-free envelope ----
    # loop effort: tank1 healthy <=10.59 V (transient) / <=10.54 V (settled)
    #              tank2 healthy <= 8.76 V (transient) / <= 9.26 V (settled)
    V_SLOW = {"tank1": 10.75, "tank2": 9.50}
    V_FAST = {"tank1": 11.05, "tank2": 9.80}
    # signed setpoint error (sp - level), positive only when the tank is starved
    # tank1 healthy up to 0.156 (transient) / 0.074 (settled)
    # tank2 healthy up to 0.153 (transient) / 0.050 (settled)
    E_MIN = {"tank1": 0.045, "tank2": 0.035}
    # genuine post-clear refill raises the level 20-45 mm per 10 s; a leaking
    # tank's level is pinned or creeps by <=7 mm per 10 s (cross-coupling).
    REFILL = 0.010
    SP_MIN = 0.05
    SP_MAX = 0.48
    MAX_DROP = 0.04
    DROP_STEP = 0.02
    RESTORE_STEP = 0.02
    SEVERE_ERR = 0.12

    m = 10 if n >= 20 else max(1, n // 2)
    mf = 4 if n >= 8 else 1

    def analyse(tank):
        eff = col(tank, "pump_effort")
        err = col(tank, "error")
        lvl = col(tank, "level")
        v_slow = mean(eff[-m:])
        e_slow = mean(err[-m:])
        v_fast = mean(eff[-mf:])
        e_fast = mean(err[-mf:])
        l_now = mean(lvl[-m:])
        l_prev = mean(lvl[-2 * m:-m])
        rise = l_now - l_prev
        hi_effort = (v_slow >= V_SLOW[tank]) or (v_fast >= V_FAST[tank])
        hi_err = (e_slow >= E_MIN[tank]) or (e_fast >= E_MIN[tank])
        # a leak pins the level while its own off-diagonal loop rails at the
        # pump limit; the only healthy look-alikes (setpoint restore, post-clear
        # wind-up) both show a fast refill, which the trend term rejects.
        anomaly = bool(hi_effort and hi_err and (rise < REFILL))
        return anomaly, v_slow, e_slow, rise

    a1, v1, e1, r1 = analyse("tank1")
    a2, v2, e2, r2 = analyse("tank2")

    def next_sp(sp, nom, anomaly, err):
        low = nom - MAX_DROP
        if low < SP_MIN:
            low = SP_MIN
        if anomaly:
            # only lower if the tank is genuinely starved (error far below sp);
            # that keeps the error signature the detector needs alive.
            if err > SEVERE_ERR:
                new = sp - DROP_STEP
            else:
                new = sp
            if new > nom:
                new = nom
            if new < low:
                new = low
        else:
            if sp < nom:
                new = sp + RESTORE_STEP
                if new > nom:
                    new = nom
            elif sp > nom:
                new = sp - RESTORE_STEP
                if new < nom:
                    new = nom
            else:
                new = sp
        if new < SP_MIN:
            new = SP_MIN
        if new > SP_MAX:
            new = SP_MAX
        return round(new, 4)

    sp1 = next_sp(sp1_in, nom1, a1, e1)
    sp2 = next_sp(sp2_in, nom2, a2, e2)

    diag = ("tank1: anomaly={} v={:.2f}V e={:+.3f} dL={:+.4f} | "
            "tank2: anomaly={} v={:.2f}V e={:+.3f} dL={:+.4f}").format(
        a1, v1, e1, r1, a2, v2, e2, r2)

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
        "anomaly_flags": {"tank1": a1, "tank2": a2},
    }
