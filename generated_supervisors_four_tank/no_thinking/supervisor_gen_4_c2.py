def supervise(telemetry_window, active_setpoints, nominal_targets):
    import math
    n = len(telemetry_window)
    if n == 0:
        return {
            "diagnosis": "empty window",
            "adjusted_setpoints": {"tank1": active_setpoints["tank1"], "tank2": active_setpoints["tank2"]},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    last = telemetry_window[-1]
    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    eff1 = [s["tank1"]["pump_effort"] for s in telemetry_window]
    eff2 = [s["tank2"]["pump_effort"] for s in telemetry_window]
    err1 = [s["tank1"]["error"] for s in telemetry_window]
    err2 = [s["tank2"]["error"] for s in telemetry_window]

    def tail(vals, k):
        m = vals[-k:] if len(vals) >= k else vals
        if not m:
            return 0.0
        return sum(m) / float(len(m))

    e1_min10 = tail(eff1, 10)
    e2_min10 = tail(eff2, 10)
    err1_mean10 = tail(err1, 10)
    err2_mean10 = tail(err2, 10)

    e1_max3 = max(eff1[-3:]) if len(eff1) >= 1 else 0.0
    e2_max3 = max(eff2[-3:]) if len(eff2) >= 1 else 0.0
    e1_win_min = min(eff1) if eff1 else 0.0
    e2_win_min = min(eff2) if eff2 else 0.0
    e1_win_max = max(eff1) if eff1 else 0.0
    e2_win_max = max(eff2) if eff2 else 0.0

    lvl1 = last["tank1"]["level"]
    lvl2 = last["tank2"]["level"]
    live_err1 = sp1 - lvl1
    live_err2 = sp2 - lvl2

    def rising_series(vals):
        cnt = 0
        m = min(len(vals), 11)
        for i in range(len(vals) - 1, len(vals) - m, -1):
            if vals[i] > vals[i - 1] + 0.02:
                cnt += 1
            else:
                break
        return cnt

    e1_rise = rising_series(eff1)
    e2_rise = rising_series(eff2)

    enter1 = (
        e1_min10 > e1_win_min + 1.2
        and e1_min10 > 9.6
        and e1_max3 >= 10.8
        and err1_mean10 > 0.07
        and live_err1 > 0.04
    ) or (
        e1_min10 > e1_win_min + 1.8
        and e1_max3 >= 11.8
        and err1_mean10 > 0.05
        and live_err1 > 0.03
    )

    enter2 = (
        e2_min10 > e2_win_min + 1.2
        and e2_min10 > 8.8
        and e2_max3 >= 9.8
        and err2_mean10 > 0.07
        and live_err2 > 0.04
    ) or (
        e2_min10 > e2_win_min + 1.8
        and e2_max3 >= 11.8
        and err2_mean10 > 0.05
        and live_err2 > 0.03
    )

    clear1 = (
        e1_min10 < e1_win_min + 0.8
        and e1_min10 < 9.4
        and err1_mean10 < 0.02
        and abs(live_err1) < 0.025
    )
    clear2 = (
        e2_min10 < e2_win_min + 0.8
        and e2_min10 < 8.8
        and err2_mean10 < 0.02
        and abs(live_err2) < 0.025
    )

    tank1_anomaly = False
    tank2_anomaly = False

    if clear1:
        tank1_anomaly = False
    elif enter1:
        tank1_anomaly = True
    elif sp1 < nom1 - 1e-9:
        tank1_anomaly = e1_min10 > 9.6 and err1_mean10 > 0.06

    if clear2:
        tank2_anomaly = False
    elif enter2:
        tank2_anomaly = True
    elif sp2 < nom2 - 1e-9:
        tank2_anomaly = e2_min10 > 8.8 and err2_mean10 > 0.06

    LOWER_STEP = 0.012
    RESTORE_STEP = 0.01

    if tank1_anomaly:
        new_sp1 = max(0.05, sp1 - LOWER_STEP) if sp1 > 0.05 else sp1
    elif sp1 < nom1:
        new_sp1 = min(nom1, sp1 + RESTORE_STEP)
    else:
        new_sp1 = sp1

    if tank2_anomaly:
        new_sp2 = max(0.05, sp2 - LOWER_STEP) if sp2 > 0.05 else sp2
    elif sp2 < nom2:
        new_sp2 = min(nom2, sp2 + RESTORE_STEP)
    else:
        new_sp2 = sp2

    return {
        "diagnosis": "t1=%s (e10=%.2f rise=%d winmin=%.2f err=%.3f live=%.3f) t2=%s (e10=%.2f rise=%d winmin=%.2f err=%.3f live=%.3f)" % (
            tank1_anomaly, e1_min10, e1_rise, e1_win_min, err1_mean10, live_err1,
            tank2_anomaly, e2_min10, e2_rise, e2_win_min, err2_mean10, live_err2),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }