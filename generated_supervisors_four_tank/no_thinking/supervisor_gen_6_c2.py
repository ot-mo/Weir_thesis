def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    last = telemetry_window[-1] if n > 0 else None

    def recent_mean(vals, k):
        if not vals:
            return 0.0
        m = vals[-k:] if len(vals) >= k else vals
        return sum(m) / float(len(m))

    eff1_series = [s["tank1"]["pump_effort"] for s in telemetry_window]
    eff2_series = [s["tank2"]["pump_effort"] for s in telemetry_window]

    eff1_recent = recent_mean(eff1_series, 5)
    eff2_recent = recent_mean(eff2_series, 5)
    sum_recent = eff1_recent + eff2_recent

    if last is None:
        return {
            "diagnosis": "empty window",
            "adjusted_setpoints": {"tank1": active_setpoints["tank1"], "tank2": active_setpoints["tank2"]},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    lvl1 = last["tank1"]["level"]
    lvl2 = last["tank2"]["level"]
    err1 = sp1 - lvl1
    err2 = sp2 - lvl2

    OWN_ENTER = 11.5
    OWN_EXIT = 9.6
    SUM_ENTER = 20.0
    SUM_EXIT = 18.5

    enter1 = (eff1_recent > OWN_ENTER) and (sum_recent > SUM_ENTER)
    enter2 = (eff2_recent > OWN_ENTER) and (sum_recent > SUM_ENTER)

    clear1 = (eff1_recent < OWN_EXIT) and (sum_recent < SUM_EXIT)
    clear2 = (eff2_recent < OWN_EXIT) and (sum_recent < SUM_EXIT)

    tank1_anomaly = enter1 and not clear1
    tank2_anomaly = enter2 and not clear2

    if sp1 < nom1 - 1e-9:
        tank1_anomaly = tank1_anomaly or not clear1
    if sp2 < nom2 - 1e-9:
        tank2_anomaly = tank2_anomaly or not clear2

    LOWER_STEP = 0.02

    if tank1_anomaly:
        new_sp1 = max(0.05, sp1 - LOWER_STEP)
    else:
        new_sp1 = nom1

    if tank2_anomaly:
        new_sp2 = max(0.05, sp2 - LOWER_STEP)
    else:
        new_sp2 = nom2

    return {
        "diagnosis": "t1=%s (eff=%.2f err=%.3f sum=%.2f); t2=%s (eff=%.2f err=%.3f)" % (
            tank1_anomaly, eff1_recent, err1, sum_recent,
            tank2_anomaly, eff2_recent, err2),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }