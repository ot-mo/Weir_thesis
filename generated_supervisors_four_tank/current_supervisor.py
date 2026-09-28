def supervise(telemetry_window, active_setpoints, nominal_targets):
    effort1 = [step["tank1"]["pump_effort"] for step in telemetry_window]
    effort2 = [step["tank2"]["pump_effort"] for step in telemetry_window]
    error1 = [step["tank1"]["error"] for step in telemetry_window]
    error2 = [step["tank2"]["error"] for step in telemetry_window]

    def median(vals):
        sv = sorted(vals)
        m = len(sv)
        if m % 2 == 1:
            return sv[m // 2]
        return (sv[m // 2 - 1] + sv[m // 2]) / 2.0

    def analyze(effort, error):
        n = len(effort)
        half = max(1, n // 2)
        baseline = median(effort[:half])
        recent = median(effort[-half:])
        avg_abs_error = sum(abs(e) for e in error[-half:]) / half
        ratio = recent / baseline if baseline > 0.2 else 1.0

        # Ratio-based (not absolute) thresholds: this plant's healthy pump
        # effort naturally oscillates from cross-coupling with the other loop
        # even with no fault, so an absolute effort/error threshold tuned for
        # a different plant's scale would misfire constantly here.
        ELEVATED_RATIO = 1.8
        ERROR_FLOOR = 0.03
        anomaly = ratio > ELEVATED_RATIO and avg_abs_error > ERROR_FLOOR
        calm = ratio < 1.2 and avg_abs_error < ERROR_FLOOR

        return anomaly, calm

    tank1_anomaly, tank1_calm = analyze(effort1, error1)
    tank2_anomaly, tank2_calm = analyze(effort2, error2)

    LOWER_STEP = 0.02
    RESTORE_STEP = 0.01

    def next_setpoint(sp, nom, anomaly, calm):
        if anomaly:
            return max(0.05, sp - LOWER_STEP)
        if calm and sp < nom:
            return min(nom, sp + RESTORE_STEP)
        return sp

    new_sp1 = next_setpoint(active_setpoints["tank1"], nominal_targets["tank1"], tank1_anomaly, tank1_calm)
    new_sp2 = next_setpoint(active_setpoints["tank2"], nominal_targets["tank2"], tank2_anomaly, tank2_calm)

    return {
        "diagnosis": f"tank1 anomaly={tank1_anomaly}; tank2 anomaly={tank2_anomaly}",
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
