def supervise(telemetry_window, active_setpoints, nominal_targets):
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

    def mean(vals):
        return sum(vals) / float(len(vals))

    eff1 = [s["tank1"]["pump_effort"] for s in telemetry_window]
    eff2 = [s["tank2"]["pump_effort"] for s in telemetry_window]
    err1 = [s["tank1"]["error"] for s in telemetry_window]
    err2 = [s["tank2"]["error"] for s in telemetry_window]
    lvl1 = [s["tank1"]["level"] for s in telemetry_window]
    lvl2 = [s["tank2"]["level"] for s in telemetry_window]

    m_eff1 = mean(eff1)
    m_eff2 = mean(eff2)
    m_err1 = mean(err1)
    m_err2 = mean(err2)
    l1 = last["tank1"]["level"]
    l2 = last["tank2"]["level"]

    T1_ENTER = 9.90
    T2_ENTER = 9.35
    T1_CLEAR = 9.55
    T2_CLEAR = 9.05

    RUN = 3

    def run_above(series, thresh):
        cnt = 0
        for v in reversed(series):
            if v > thresh:
                cnt += 1
            else:
                break
        return cnt

    def run_below(series, thresh):
        cnt = 0
        for v in reversed(series):
            if v < thresh:
                cnt += 1
            else:
                break
        return cnt

    enter1 = (m_eff1 > T1_ENTER) and (run_above(eff1, T1_ENTER) >= RUN)
    enter2 = (m_eff2 > T2_ENTER) and (run_above(eff2, T2_ENTER) >= RUN)

    clear1 = (m_eff1 < T1_CLEAR) and (run_below(eff1, T1_CLEAR) >= RUN) and (m_err1 < 0.030)
    clear2 = (m_eff2 < T2_CLEAR) and (run_below(eff2, T2_CLEAR) >= RUN) and (m_err2 < 0.030)

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
        new_sp1 = max(0.05, sp1 - LOWER_STEP)
    elif clear1 and sp1 < nom1:
        new_sp1 = min(nom1, sp1 + RESTORE_STEP)
    else:
        new_sp1 = sp1

    if tank2_anomaly:
        new_sp2 = max(0.05, sp2 - LOWER_STEP)
    elif clear2 and sp2 < nom2:
        new_sp2 = min(nom2, sp2 + RESTORE_STEP)
    else:
        new_sp2 = sp2

    return {
        "diagnosis": "tank1 anomaly=%s (eff1=%.2f err1=%.3f lvl1=%.3f); tank2 anomaly=%s (eff2=%.2f err2=%.3f lvl2=%.3f)" % (
            tank1_anomaly, m_eff1, m_err1, l1, tank2_anomaly, m_eff2, m_err2, l2),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
