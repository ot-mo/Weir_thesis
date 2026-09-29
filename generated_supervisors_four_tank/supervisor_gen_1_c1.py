def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    k = 10
    if n < k:
        k = max(1, n)
    recent = telemetry_window[-k:]
    older = telemetry_window[max(0, n - 2 * k):n - k]
    if len(older) == 0:
        older = recent

    def _mean(vals):
        total = 0.0
        for v in vals:
            total += v
        return total / float(len(vals))

    eff1 = _mean([s["tank1"]["pump_effort"] for s in recent])
    eff2 = _mean([s["tank2"]["pump_effort"] for s in recent])
    err1 = _mean([s["tank1"]["error"] for s in recent])
    err2 = _mean([s["tank2"]["error"] for s in recent])
    err1_prev = _mean([s["tank1"]["error"] for s in older])
    err2_prev = _mean([s["tank2"]["error"] for s in older])
    lvl1 = _mean([s["tank1"]["level"] for s in recent])
    lvl2 = _mean([s["tank2"]["level"] for s in recent])
    lvl1_prev = _mean([s["tank1"]["level"] for s in older])
    lvl2_prev = _mean([s["tank2"]["level"] for s in older])

    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]
    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]

    mitigating1 = sp1 < nom1 - 0.005
    mitigating2 = sp2 < nom2 - 0.005

    THR1 = 11.6 if mitigating1 else 10.9
    THR2 = 11.6 if mitigating2 else 10.5

    RECOV_ERR = 0.02
    RECOV_LVL = 0.012

    recovering1 = (err1 < err1_prev - RECOV_ERR) or (lvl1 > lvl1_prev + RECOV_LVL)
    recovering2 = (err2 < err2_prev - RECOV_ERR) or (lvl2 > lvl2_prev + RECOV_LVL)

    anom1 = (eff1 >= THR1) and (not recovering1)
    anom2 = (eff2 >= THR2) and (not recovering2)

    LOWER_STEP = 0.01
    RESTORE_STEP = 0.005
    MAX_LOWER = 0.10
    ERR_GATE = 0.10

    def next_sp(sp, nom, anom, err, eff, rest_gate):
        floor = nom - MAX_LOWER
        if floor < 0.05:
            floor = 0.05
        if anom:
            if err > ERR_GATE and sp > floor:
                nxt = sp - LOWER_STEP
                if nxt < floor:
                    nxt = floor
                return nxt
            return sp
        if sp < nom and eff < rest_gate:
            nxt = sp + RESTORE_STEP
            if nxt > nom:
                nxt = nom
            return nxt
        return sp

    new_sp1 = next_sp(sp1, nom1, anom1, err1, eff1, 10.0)
    new_sp2 = next_sp(sp2, nom2, anom2, err2, eff2, 9.6)

    diagnosis = (
        "tank1 flag=%s (loop drive mean %.2f V, threshold %.2f V); "
        "tank2 flag=%s (loop drive mean %.2f V, threshold %.2f V)"
    ) % (anom1, eff1, THR1, anom2, eff2, THR2)

    return {
        "diagnosis": diagnosis,
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": anom1, "tank2": anom2},
    }