def supervise(telemetry_window, active_setpoints, nominal_targets):
    effort1 = [step["tank1"]["pump_effort"] for step in telemetry_window]
    effort2 = [step["tank2"]["pump_effort"] for step in telemetry_window]

    def mean(vals):
        return sum(vals) / float(len(vals))

    def frac_above(vals, thr):
        n = 0
        for v in vals:
            if v > thr:
                n += 1
        return n / float(len(vals))

    m1 = mean(effort1)
    m2 = mean(effort2)
    f1 = frac_above(effort1, 10.8)
    f2 = frac_above(effort2, 9.5)

    tank1_anomaly = (m1 > 11.0) or (m1 > 10.8 and f1 > 0.25)
    tank2_anomaly = (m2 > 9.8) or (m2 > 9.5 and f2 > 0.25)

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    LOWER_STEP = 0.02
    RESTORE_STEP = 0.01

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
        "diagnosis": "tank1 anomaly=%s (mean=%.2f frac=%.2f); tank2 anomaly=%s (mean=%.2f frac=%.2f)" % (tank1_anomaly, m1, f1, tank2_anomaly, m2, f2),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }