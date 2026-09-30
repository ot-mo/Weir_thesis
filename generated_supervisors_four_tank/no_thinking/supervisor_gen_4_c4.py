def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    if n == 0 or telemetry_window[-1] is None:
        return {
            "diagnosis": "empty window",
            "adjusted_setpoints": {"tank1": active_setpoints["tank1"], "tank2": active_setpoints["tank2"]},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    eff1_series = [s["tank1"]["pump_effort"] for s in telemetry_window]
    eff2_series = [s["tank2"]["pump_effort"] for s in telemetry_window]
    lvl1_series = [s["tank1"]["level"] for s in telemetry_window]
    lvl2_series = [s["tank2"]["level"] for s in telemetry_window]

    def tail(vals, k):
        return vals[-k:] if len(vals) >= k else vals

    def mean(vals):
        return sum(vals) / float(len(vals)) if vals else 0.0

    def deficit_count(lvls, sp, k, margin):
        vals = tail(lvls, k)
        return sum(1 for v in vals if (sp - v) > margin)

    K = 8
    eff1_mean = mean(tail(eff1_series, K))
    eff2_mean = mean(tail(eff2_series, K))
    lvl1 = telemetry_window[-1]["tank1"]["level"]
    lvl2 = telemetry_window[-1]["tank2"]["level"]

    EFF1_LEAK = 10.9
    EFF2_LEAK = 9.6
    EFF1_CLEAR = 10.4
    EFF2_CLEAR = 9.4
    LEVEL_MARGIN = 0.04
    DEFICIT_REQ = 5

    d1 = deficit_count(lvl1_series, sp1, K, LEVEL_MARGIN)
    d2 = deficit_count(lvl2_series, sp2, K, LEVEL_MARGIN)

    leak1 = (eff1_mean > EFF1_LEAK) and (d1 >= DEFICIT_REQ)
    leak2 = (eff2_mean > EFF2_LEAK) and (d2 >= DEFICIT_REQ)

    clear1 = (eff1_mean < EFF1_CLEAR) or (d1 <= 1)
    clear2 = (eff2_mean < EFF2_CLEAR) or (d2 <= 1)

    tank1_anomaly = False
    tank2_anomaly = False

    if sp1 < nom1 - 1e-9:
        tank1_anomaly = not clear1
    if leak1:
        tank1_anomaly = True

    if sp2 < nom2 - 1e-9:
        tank2_anomaly = not clear2
    if leak2:
        tank2_anomaly = True

    LOWER_STEP = 0.02
    RESTORE_STEP = 0.015

    if tank1_anomaly:
        new_sp1 = max(0.05, sp1 - LOWER_STEP)
    elif sp1 < nom1:
        new_sp1 = min(nom1, sp1 + RESTORE_STEP)
    else:
        new_sp1 = sp1

    if tank2_anomaly:
        new_sp2 = max(0.05, sp2 - LOWER_STEP)
    elif sp2 < nom2:
        new_sp2 = min(nom2, sp2 + RESTORE_STEP)
    else:
        new_sp2 = sp2

    return {
        "diagnosis": "t1=%s(eff=%.2f def=%d) t2=%s(eff=%.2f def=%d)" % (
            tank1_anomaly, eff1_mean, d1, tank2_anomaly, eff2_mean, d2),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
