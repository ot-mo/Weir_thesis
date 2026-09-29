def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    if n < 6:
        return {
            "diagnosis": "insufficient telemetry",
            "adjusted_setpoints": {"tank1": active_setpoints["tank1"],
                                   "tank2": active_setpoints["tank2"]},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    k = 10 if n >= 30 else max(2, n // 3)

    def mean(vals):
        return sum(vals) / float(len(vals))

    def col(tank, field):
        return [step[tank][field] for step in telemetry_window]

    # Thresholds anchored on the measured healthy envelopes of this plant.
    # Healthy 10-sample means can never exceed the healthy instantaneous
    # maxima, so these are upper bounds on anything fault-free.
    EFF_HI = {"tank1": 10.70, "tank2": 9.80}    # healthy <=10.54 / <=9.26 V
    ERR_HI = {"tank1": 0.085, "tank2": 0.075}   # healthy settled |e| <=0.074 / <=0.050
    EFF_SAT = {"tank1": 11.40, "tank2": 11.40}  # pumps limited to 12 V
    ERR_MIN = 0.030
    RISE = 0.003            # m per k samples that still counts as "refilling"
    LOWER_STEP = 0.02
    RESTORE_STEP = 0.02
    MAX_DROP = 0.04
    SP_MIN = 0.05
    SP_MAX = 0.48

    def analyse(tank):
        eff = col(tank, "pump_effort")
        err = col(tank, "error")
        lvl = col(tank, "level")

        v_now = mean(eff[-k:])
        e_now = mean([abs(e) for e in err[-k:]])
        l_now = mean(lvl[-k:])
        l_prev = mean(lvl[-2 * k:-k])
        drift = l_now - l_prev
        rising = drift > RISE

        # A leak shows up as: this loop's own effort above anything the
        # healthy plant produces, with a level error the loop cannot close,
        # while the tank is no longer filling.  The level-trend guard keeps
        # out the two legitimate look-alikes: the start-up transient (big
        # error, but level rising) and the post-fault wind-up recovery
        # (effort at the 12 V rail, but level rising fast).
        high_effort = (v_now > EFF_HI[tank]) and (e_now > ERR_HI[tank])
        saturated = (v_now > EFF_SAT[tank]) and (e_now > ERR_MIN)
        anomaly = (not rising) and (high_effort or saturated)
        return anomaly, v_now, e_now, drift

    a1, v1, e1, d1 = analyse("tank1")
    a2, v2, e2, d2 = analyse("tank2")

    def next_sp(sp, nom, anomaly):
        low = nom - MAX_DROP
        if low < SP_MIN:
            low = SP_MIN
        if anomaly:
            new = sp - LOWER_STEP
            if new < low:
                new = low
        elif sp < nom:
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

    sp1 = next_sp(active_setpoints["tank1"], nominal_targets["tank1"], a1)
    sp2 = next_sp(active_setpoints["tank2"], nominal_targets["tank2"], a2)

    diag = ("tank1: anomaly={} v={:.2f}V |e|={:.3f} dL={:+.4f} | "
            "tank2: anomaly={} v={:.2f}V |e|={:.3f} dL={:+.4f}").format(
        a1, v1, e1, d1, a2, v2, e2, d2)

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
        "anomaly_flags": {"tank1": a1, "tank2": a2},
    }
