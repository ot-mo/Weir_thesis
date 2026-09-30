def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    if n == 0:
        return {
            "diagnosis": "empty window",
            "adjusted_setpoints": {"tank1": active_setpoints["tank1"], "tank2": active_setpoints["tank2"]},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    def mean(vals):
        if not vals:
            return 0.0
        return sum(vals) / float(len(vals))

    eff1 = [s["tank1"]["pump_effort"] for s in telemetry_window]
    eff2 = [s["tank2"]["pump_effort"] for s in telemetry_window]
    last5_eff1 = mean(eff1[-5:])
    last5_eff2 = mean(eff2[-5:])
    last10_eff1 = mean(eff1[-10:])
    last10_eff2 = mean(eff2[-10:])

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    lvl1 = telemetry_window[-1]["tank1"]["level"]
    lvl2 = telemetry_window[-1]["tank2"]["level"]
    err1 = sp1 - lvl1
    err2 = sp2 - lvl2

    def mean_abs_err(series_index, key, k):
        vals = []
        for s in telemetry_window[-k:]:
            vals.append(abs(s[key]["error"]))
        return mean(vals)

    mae1 = mean_abs_err(0, "tank1", 5)
    mae2 = mean_abs_err(0, "tank2", 5)

    EFF1_HI = 10.6
    EFF2_HI = 9.55
    ERR_HI = 0.020

    EFF1_EXIT = 9.4
    EFF2_EXIT = 8.6
    ERR_EXIT = 0.015

    DEF1 = sp1 - lvl1
    DEF2 = sp2 - lvl2

    enter1 = (last5_eff1 > EFF1_HI) and (mae1 > ERR_HI) and (DEF1 > 0.010)
    enter2 = (last5_eff2 > EFF2_HI) and (mae2 > ERR_HI) and (DEF2 > 0.010)

    trimmed1 = sp1 < nom1 - 1e-9
    trimmed2 = sp2 < nom2 - 1e-9

    tail10_low1 = last10_eff1 < EFF1_EXIT
    tail10_low2 = last10_eff2 < EFF2_EXIT

    tail_deficit1 = DEF1 < ERR_EXIT
    tail_deficit2 = DEF2 < ERR_EXIT

    clear1 = (sp1 <= 0.055) and tail10_low1 and tail_deficit1
    clear2 = (sp2 <= 0.055) and tail10_low2 and tail_deficit2

    if trimmed1:
        tank1_anomaly = not clear1
    else:
        tank1_anomaly = enter1

    if trimmed2:
        tank2_anomaly = not clear2
    else:
        tank2_anomaly = enter2

    if not tank1_anomaly and not trimmed1:
        tank1_anomaly = False

    LOWER_STEP = 0.008
    NOM_GAP_MAX = 0.020

    if tank1_anomaly:
        target1 = max(0.05, nom1 - NOM_GAP_MAX)
        if sp1 > target1 + 1e-9:
            new_sp1 = max(target1, sp1 - LOWER_STEP)
            new_sp1 = max(0.05, new_sp1)
        else:
            new_sp1 = sp1
    elif sp1 < nom1 - 1e-9:
        new_sp1 = min(nom1, sp1 + LOWER_STEP * 2.0)
    else:
        new_sp1 = sp1

    if tank2_anomaly:
        target2 = max(0.05, nom2 - NOM_GAP_MAX)
        if sp2 > target2 + 1e-9:
            new_sp2 = max(target2, sp2 - LOWER_STEP)
            new_sp2 = max(0.05, new_sp2)
        else:
            new_sp2 = sp2
    elif sp2 < nom2 - 1e-9:
        new_sp2 = min(nom2, sp2 + LOWER_STEP * 2.0)
    else:
        new_sp2 = sp2

    return {
        "diagnosis": "t1=%s eff1=%.2f def1=%.3f; t2=%s eff2=%.2f def2=%.3f" % (
            tank1_anomaly, last5_eff1, DEF1, tank2_anomaly, last5_eff2, DEF2),
        "adjusted_setpoints": {"tank1": float(new_sp1), "tank2": float(new_sp2)},
        "anomaly_flags": {"tank1": bool(tank1_anomaly), "tank2": bool(tank2_anomaly)},
    }
