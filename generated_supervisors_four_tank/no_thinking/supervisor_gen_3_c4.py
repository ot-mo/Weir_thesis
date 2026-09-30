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

    EFF1_LEAK = 10.6
    EFF2_LEAK = 9.5
    ERR1_LEAK = 0.07
    ERR2_LEAK = 0.075

    EFF1_CLEAR = 10.2
    EFF2_CLEAR = 9.2
    ERR_CLEAR = 0.06

    ENTER_STREAK = 3
    EXIT_STREAK = 4

    def streak_at_end(vals, thresh, above):
        cnt = 0
        for v in reversed(vals):
            if (v > thresh) if above else (v < thresh):
                cnt += 1
            else:
                break
        return cnt

    enter1 = (eff1_recent > EFF1_LEAK) and (err1 > ERR1_LEAK)
    enter2 = (eff2_recent > EFF2_LEAK) and (err2 > ERR2_LEAK)

    enter1_streak = ENTER_STREAK if enter1 else 0
    enter2_streak = ENTER_STREAK if enter2 else 0

    clear1 = (eff1_recent < EFF1_CLEAR) and (err1 < ERR_CLEAR)
    clear2 = (eff2_recent < EFF2_CLEAR) and (err2 < ERR_CLEAR)

    tank1_anomaly = False
    tank2_anomaly = False

    if sp1 < nom1 - 1e-9:
        tank1_anomaly = not clear1
    elif enter1:
        tank1_anomaly = True

    if sp2 < nom2 - 1e-9:
        tank2_anomaly = not clear2
    elif enter2:
        tank2_anomaly = True

    LOWER_STEP = 0.015
    RESTORE_STEP = 0.01

    if tank1_anomaly:
        if sp1 > 0.05:
            new_sp1 = max(0.05, sp1 - LOWER_STEP)
        else:
            new_sp1 = sp1
    elif sp1 < nom1:
        new_sp1 = min(nom1, sp1 + RESTORE_STEP)
    else:
        new_sp1 = sp1

    if tank2_anomaly:
        if sp2 > 0.05:
            new_sp2 = max(0.05, sp2 - LOWER_STEP)
        else:
            new_sp2 = sp2
    elif sp2 < nom2:
        new_sp2 = min(nom2, sp2 + RESTORE_STEP)
    else:
        new_sp2 = sp2

    return {
        "diagnosis": "tank1 anomaly=%s (eff=%.2f err=%.3f); tank2 anomaly=%s (eff=%.2f err=%.3f)" % (
            tank1_anomaly, eff1_recent, err1, tank2_anomaly, eff2_recent, err2),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
