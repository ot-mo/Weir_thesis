def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    if n < 12:
        return {
            "diagnosis": "insufficient telemetry",
            "adjusted_setpoints": {"tank1": active_setpoints["tank1"],
                                   "tank2": active_setpoints["tank2"]},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    def mean(vals):
        return sum(vals) / float(len(vals))

    def col(tank, field):
        return [step[tank][field] for step in telemetry_window]

    m = n
    i4 = m - 4
    i10 = m - 10

    # Effort cuts sit strictly between the measured healthy maxima of the
    # fault-free episode (tank1: 10.59 V start-up, 10.54 V settled; tank2:
    # 8.76 V / 9.26 V) and the 12 V pump rail.  A leak always pins the
    # leaking tank's OWN off-diagonal loop (tank1 leak -> pump2, tank2 leak
    # -> pump1) because even a 1.5x outlet area cannot be fed at the
    # nominal setpoint with both pumps at their limits.
    V_FAST = {"tank1": 10.95, "tank2": 10.05}
    V_RAIL = {"tank1": 11.20, "tank2": 11.20}
    E_FAST = {"tank1": 0.035, "tank2": 0.030}
    E_RAIL = {"tank1": 0.010, "tank2": 0.010}

    # Refilling gate is a minimum rate, not "any positive drift": a leaking
    # tank relaxing to its leak equilibrium creeps up at only 0.2-0.3 mm/s,
    # while a tank whose leak just stopped refills at 3-6 mm/s.
    RISE_5 = 0.004

    LOWER_STEP = 0.02
    RESTORE_STEP = 0.03
    MAX_DROP = 0.04
    SP_MIN = 0.05
    SP_MAX = 0.48

    def analyse(tank):
        eff = col(tank, "pump_effort")
        err = col(tank, "error")
        lvl = col(tank, "level")

        v_f = mean(eff[i4:])
        e_f = mean([abs(x) for x in err[i4:]])
        v_s = mean(eff[i10:])
        e_s = mean([abs(x) for x in err[i10:]])
        rise = lvl[m - 1] - lvl[m - 6]

        refilling = rise > RISE_5
        fast = (v_f > V_FAST[tank]) and (e_f > E_FAST[tank])
        pinned = (v_s > V_RAIL[tank]) and (e_s > E_RAIL[tank])
        anomaly = (not refilling) and (fast or pinned)
        return anomaly, v_s, e_s, rise

    a1, v1, e1, r1 = analyse("tank1")
    a2, v2, e2, r2 = analyse("tank2")

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

    diag = ("tank1: anom={} v10={:.2f}V |e|10={:.3f} dL5={:+.4f} | "
            "tank2: anom={} v10={:.2f}V |e|10={:.3f} dL5={:+.4f}").format(
        a1, v1, e1, r1, a2, v2, e2, r2)

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
        "anomaly_flags": {"tank1": a1, "tank2": a2},
    }
