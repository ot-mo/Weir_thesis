def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    if n == 0:
        return {
            "diagnosis": "empty window",
            "adjusted_setpoints": {"tank1": active_setpoints["tank1"], "tank2": active_setpoints["tank2"]},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    def series(tank, key):
        return [s[tank][key] for s in telemetry_window]

    def mean(vals):
        if not vals:
            return 0.0
        return sum(vals) / float(len(vals))

    eff1s = series("tank1", "pump_effort")
    eff2s = series("tank2", "pump_effort")
    err1s = series("tank1", "error")
    err2s = series("tank2", "error")

    eff1_10 = mean(eff1s[-10:])
    eff2_10 = mean(eff2s[-10:])
    me1 = mean([abs(e) for e in err1s[-10:]])
    me2 = mean([abs(e) for e in err2s[-10:]])

    base1 = mean(eff1s[:-15]) if n > 20 else mean(eff1s[:max(1, n - 15)])
    base2 = mean(eff2s[:-15]) if n > 20 else mean(eff2s[:max(1, n - 15)])

    CLAMP = 12.0
    NEAR_CLAMP = 11.70
    JUMP = 1.6
    ERR_GATE = 0.035
    ASYM = 1.8
    HEALTHY_EFF1 = 9.35
    HEALTHY_EFF2 = 8.96

    jump1 = eff1_10 - base1
    jump2 = eff2_10 - base2

    asym1 = abs(eff2_10 - HEALTHY_EFF2) - abs(eff1_10 - HEALTHY_EFF1)
    asym2 = abs(eff1_10 - HEALTHY_EFF1) - abs(eff2_10 - HEALTHY_EFF2)

    enter1 = (eff1_10 >= NEAR_CLAMP or jump1 >= JUMP or asym1 >= ASYM) and (me1 >= ERR_GATE)
    enter2 = (eff2_10 >= NEAR_CLAMP or jump2 >= JUMP or asym2 >= ASYM) and (me2 >= ERR_GATE)

    clear1 = (asym1 <= 0.9) and (me1 <= 0.045)
    clear2 = (asym2 <= 0.9) and (me2 <= 0.045)

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    trim1 = sp1 < nom1 - 1e-9
    trim2 = sp2 < nom2 - 1e-9

    tank1_anomaly = enter1 or trim1
    tank2_anomaly = enter2 or trim2

    if tank1_anomaly and clear1:
        tank1_anomaly = False
    if tank2_anomaly and clear2:
        tank2_anomaly = False

    LOWER_STEP = 0.02
    RESTORE_STEP = 0.02
    LOW_LIMIT = 0.05

    if tank1_anomaly:
        new_sp1 = max(LOW_LIMIT, sp1 - LOWER_STEP) if sp1 > LOW_LIMIT else sp1
    elif sp1 < nom1:
        new_sp1 = min(nom1, sp1 + RESTORE_STEP)
    else:
        new_sp1 = sp1

    if tank2_anomaly:
        new_sp2 = max(LOW_LIMIT, sp2 - LOWER_STEP) if sp2 > LOW_LIMIT else sp2
    elif sp2 < nom2:
        new_sp2 = min(nom2, sp2 + RESTORE_STEP)
    else:
        new_sp2 = sp2

    return {
        "diagnosis": "tank1=%s (e10=%.2f b=%.2f j=%.2f a=%.2f m=%.3f); tank2=%s (e10=%.2f b=%.2f j=%.2f a=%.2f m=%.3f)" % (
            tank1_anomaly, eff1_10, base1, jump1, asym1, me1, tank2_anomaly, eff2_10, base2, jump2, asym2, me2),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
