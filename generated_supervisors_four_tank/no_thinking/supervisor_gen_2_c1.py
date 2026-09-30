def supervise(telemetry_window, active_setpoints, nominal_targets):
    effort1 = [step["tank1"]["pump_effort"] for step in telemetry_window]
    effort2 = [step["tank2"]["pump_effort"] for step in telemetry_window]
    n = len(effort1)
    half = max(1, n // 2)
    def mean(vals):
        return sum(vals) / len(vals)
    eff1_recent = mean(effort1[-half:])
    eff2_recent = mean(effort2[-half:])
    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    # Effort-only thresholds, derived from measured healthy ranges:
    # tank1: settled max 10.54 V, start-up max 10.59 V -> 11.0 V safe.
    # tank2: settled max 9.26 V, start-up max 8.76 V -> 9.5 V safe.
    THRESH1 = 11.0
    THRESH2 = 9.5
    tank1_anomaly = eff1_recent > THRESH1
    tank2_anomaly = eff2_recent > THRESH2
    # Restore when effort falls well below thresholds.
    CALM1 = 10.5
    CALM2 = 9.0
    tank1_calm = eff1_recent < CALM1
    tank2_calm = eff2_recent < CALM2
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
            "tank1: eff=%.2f anomaly=%s; tank2: eff=%.2f anomaly=%s"
            % (eff1_recent, tank1_anomaly, eff2_recent, tank2_anomaly)
        ),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
