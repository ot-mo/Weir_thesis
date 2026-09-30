def supervise(telemetry_window, active_setpoints, nominal_targets):
    effort1 = [step["tank1"]["pump_effort"] for step in telemetry_window]
    effort2 = [step["tank2"]["pump_effort"] for step in telemetry_window]

    def has_consecutive_above(vals, threshold, count):
        streak = 0
        for v in vals:
            if v > threshold:
                streak += 1
                if streak >= count:
                    return True
            else:
                streak = 0
        return False

    EFFORT_THRESHOLD = 11.5

    tank1_anomaly = has_consecutive_above(effort1, EFFORT_THRESHOLD, 2)
    tank2_anomaly = has_consecutive_above(effort2, EFFORT_THRESHOLD, 2)

    eff1_low = all(e < 10.6 for e in effort1[-3:]) if len(effort1) >= 3 else False
    eff2_low = all(e < 10.6 for e in effort2[-3:]) if len(effort2) >= 3 else False

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    LOWER_STEP = 0.02
    RESTORE_STEP = 0.01

    if tank1_anomaly:
        new_sp1 = max(0.05, sp1 - LOWER_STEP)
    elif eff1_low and sp1 < nom1:
        new_sp1 = min(nom1, sp1 + RESTORE_STEP)
    else:
        new_sp1 = sp1

    if tank2_anomaly:
        new_sp2 = max(0.05, sp2 - LOWER_STEP)
    elif eff2_low and sp2 < nom2:
        new_sp2 = min(nom2, sp2 + RESTORE_STEP)
    else:
        new_sp2 = sp2

    return {
        "diagnosis": "tank1 anomaly=%s; tank2 anomaly=%s" % (tank1_anomaly, tank2_anomaly),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }