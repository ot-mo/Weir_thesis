def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    if n == 0:
        return {
            "diagnosis": "empty window",
            "adjusted_setpoints": {"tank1": active_setpoints["tank1"], "tank2": active_setpoints["tank2"]},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    last = telemetry_window[-1]
    eff1 = [s["tank1"]["pump_effort"] for s in telemetry_window]
    eff2 = [s["tank2"]["pump_effort"] for s in telemetry_window]
    lvl1 = [s["tank1"]["level"] for s in telemetry_window]
    lvl2 = [s["tank2"]["level"] for s in telemetry_window]

    def mean(vals):
        if not vals:
            return 0.0
        return sum(vals) / float(len(vals))

    k = min(10, n)
    m_eff1 = mean(eff1[-k:])
    m_eff2 = mean(eff2[-k:])
    m_lvl1 = mean(lvl1[-k:])
    m_lvl2 = mean(lvl2[-k:])

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    # Mask start-up: if levels have risen significantly during the window we are in transient
    start_up = (m_lvl1 < 0.50 * nom1 + 0.5 * lvl1[0]) and (lvl1[-1] - lvl1[0] > 0.005 or lvl2[-1] - lvl2[0] > 0.005) if n > 1 else False
    # Simpler: consider start-up if first level is far below setpoint and level is rising
    rising1 = n > 1 and lvl1[-1] - lvl1[0] > 0.002
    rising2 = n > 1 and lvl2[-1] - lvl2[0] > 0.002
    transient = (lvl1[0] < 0.85 * sp1) and (lvl1[-1] < 0.95 * sp1) and rising1
    transient2 = (lvl2[0] < 0.85 * sp2) and (lvl2[-1] < 0.95 * sp2) and rising2

    # High-effort entry thresholds (healthy max: t1~10.54 settled, 10.59 startup), err entry
    EFF1_ENTRY = 11.0
    EFF2_ENTRY = 10.5
    ERR1_ENTRY = 0.060
    ERR2_ENTRY = 0.055
    EFF1_CLEAR = 9.8
    EFF2_CLEAR = 9.6
    ERR_CLEAR = 0.045

    err1 = sp1 - last["tank1"]["level"]
    err2 = sp2 - last["tank2"]["level"]

    # Entry conditions (sustained over window)
    enter1 = (m_eff1 > EFF1_ENTRY) and (not transient)
    enter2 = (m_eff2 > EFF2_ENTRY) and (not transient2)

    # If error is large positive it reinforces; but the primary is sustained high effort
    if not enter1 and m_eff1 > EFF1_ENTRY - 0.4 and err1 > ERR1_ENTRY and not transient:
        enter1 = True
    if not enter2 and m_eff2 > EFF2_ENTRY - 0.4 and err2 > ERR2_ENTRY and not transient2:
        enter2 = True

    # Clear conditions: sustained effort and error below clear thresholds
    clear1 = (m_eff1 < EFF1_CLEAR) and (abs(err1) < ERR_CLEAR)
    clear2 = (m_eff2 < EFF2_CLEAR) and (abs(err2) < ERR_CLEAR)

    tank1_anomaly = False
    tank2_anomaly = False

    # Persistent state via setpoint: if we already lowered sp, keep flag unless clearly cleared
    if sp1 < nom1 - 1e-9:
        tank1_anomaly = not clear1
    elif enter1:
        tank1_anomaly = True

    if sp2 < nom2 - 1e-9:
        tank2_anomaly = not clear2
    elif enter2:
        tank2_anomaly = True

    LOWER_STEP = 0.020
    RESTORE_STEP = 0.020

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
        "diagnosis": "t1a=%s eff1m=%.2f err1=%.3f t2a=%s eff2m=%.2f err2=%.3f" % (
            tank1_anomaly, m_eff1, err1, tank2_anomaly, m_eff2, err2),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }