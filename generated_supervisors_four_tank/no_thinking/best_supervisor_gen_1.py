def supervise(telemetry_window, active_setpoints, nominal_targets):
    effort1 = [step["tank1"]["pump_effort"] for step in telemetry_window]
    effort2 = [step["tank2"]["pump_effort"] for step in telemetry_window]
    error1 = [step["tank1"]["error"] for step in telemetry_window]
    error2 = [step["tank2"]["error"] for step in telemetry_window]
    level1 = [step["tank1"]["level"] for step in telemetry_window]
    level2 = [step["tank2"]["level"] for step in telemetry_window]

    n = len(error1)
    half = max(1, n // 2)

    def mean(vals):
        return sum(vals) / len(vals)

    # Absolute thresholds from measured healthy ranges (settled mean|error|
    # tank1=0.0154, tank2=0.0202; settled effort max 10.54 V tank1 / 9.26 V
    # tank2). Start-up can reach effort 10.59 V, so require BOTH high error
    # and saturation to avoid start-up false positives.
    ERROR_THRESHOLD = 0.09
    EFFORT_THRESHOLD = 11.0

    err1_recent = mean([abs(e) for e in error1[-half:]])
    err2_recent = mean([abs(e) for e in error2[-half:]])
    eff1_recent = mean(effort1[-half:])
    eff2_recent = mean(effort2[-half:])

    lvl1 = level1[-1]
    lvl2 = level2[-1]
    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]

    # A leak makes the leaking tank's own PI loop saturate (12 V) while the
    # error grows well beyond healthy settled values. Require both conditions.
    tank1_anomaly = (err1_recent > ERROR_THRESHOLD and eff1_recent > EFFORT_THRESHOLD
                     and (sp1 - lvl1) > 0.05)
    tank2_anomaly = (err2_recent > ERROR_THRESHOLD and eff2_recent > EFFORT_THRESHOLD
                     and (sp2 - lvl2) > 0.05)

    # Relaxed calm condition for restore: error and effort both back in healthy bands.
    tank1_calm = err1_recent < 0.035 and eff1_recent < 10.6
    tank2_calm = err2_recent < 0.035 and eff2_recent < 10.6

    LOWER_STEP = 0.02
    RESTORE_STEP = 0.01

    def next_setpoint(sp, nom, anomaly, calm):
        if anomaly:
            return max(0.05, sp - LOWER_STEP)
        if calm and sp < nom:
            return min(nom, sp + RESTORE_STEP)
        return sp

    new_sp1 = next_setpoint(sp1, nominal_targets["tank1"], tank1_anomaly, tank1_calm)
    new_sp2 = next_setpoint(sp2, nominal_targets["tank2"], tank2_anomaly, tank2_calm)

    return {
        "diagnosis": (
            "tank1: err=%.3f eff=%.2f anomaly=%s; tank2: err=%.3f eff=%.2f anomaly=%s"
            % (err1_recent, eff1_recent, tank1_anomaly, err2_recent, eff2_recent, tank2_anomaly)
        ),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
