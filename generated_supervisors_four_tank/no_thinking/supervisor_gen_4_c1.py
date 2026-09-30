def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    last = telemetry_window[-1] if n > 0 else None

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

    def recent_mean(vals, k):
        if not vals:
            return 0.0
        m = vals[-k:] if len(vals) >= k else vals
        return sum(m) / float(len(m))

    eff1_series = [s["tank1"]["pump_effort"] for s in telemetry_window]
    eff2_series = [s["tank2"]["pump_effort"] for s in telemetry_window]

    eff1_recent = recent_mean(eff1_series, 5)
    eff2_recent = recent_mean(eff2_series, 5)

    ENTER_EFF1 = 11.2
    ENTER_EFF2 = 10.5
    ENTER_MIN_ERR1 = 0.025
    ENTER_MIN_ERR2 = 0.030

    CLEAR_EFF1 = 9.7
    CLEAR_EFF2 = 8.9
    CLEAR_LEVEL_TOL = 0.03

    LEVEL_FLOOR_TOL = 0.02

    def streak_above(vals, thresh):
        cnt = 0
        for v in reversed(vals):
            if v > thresh:
                cnt += 1
            else:
                break
        return cnt

    def streak_below(vals, thresh):
        cnt = 0
        for v in reversed(vals):
            if v < thresh:
                cnt += 1
            else:
                break
        return cnt

    enter1 = streak_above(eff1_series, ENTER_EFF1) >= 3
    enter2 = streak_above(eff2_series, ENTER_EFF2) >= 3

    clear1 = (streak_below(eff1_series, CLEAR_EFF1) >= 4) and (abs(sp1 - nom1) < CLEAR_LEVEL_TOL or err1 < 0.01)
    clear2 = (streak_below(eff2_series, CLEAR_EFF2) >= 4) and (abs(sp2 - nom2) < CLEAR_LEVEL_TOL or err2 < 0.01)

    tank1_anomaly = False
    tank2_anomaly = False

    if sp1 < nom1 - 1e-9:
        tank1_anomaly = not clear1
    elif enter1 and (err1 > ENTER_MIN_ERR1 or lvl1 < sp1 - LEVEL_FLOOR_TOL):
        tank1_anomaly = True
    else:
        tank1_anomaly = enter1

    if sp2 < nom2 - 1e-9:
        tank2_anomaly = not clear2
    elif enter2 and (err2 > ENTER_MIN_ERR2 or lvl2 < sp2 - LEVEL_FLOOR_TOL):
        tank2_anomaly = True
    else:
        tank2_anomaly = enter2

    if tank1_anomaly:
        new_sp1 = max(0.05, sp1 - 0.015)
    else:
        new_sp1 = min(nom1, sp1 + 0.02)

    if tank2_anomaly:
        new_sp2 = max(0.05, sp2 - 0.015)
    else:
        new_sp2 = min(nom2, sp2 + 0.02)

    return {
        "diagnosis": "tank1 anomaly=%s (eff=%.2f err=%.3f level=%.3f sp=%.3f); tank2 anomaly=%s (eff=%.2f err=%.3f level=%.3f sp=%.3f)" % (
            tank1_anomaly, eff1_recent, err1, lvl1, new_sp1, tank2_anomaly, eff2_recent, err2, lvl2, new_sp2),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }