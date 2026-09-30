def supervise(telemetry_window, active_setpoints, nominal_targets):
    effort1 = [step["tank1"]["pump_effort"] for step in telemetry_window]
    effort2 = [step["tank2"]["pump_effort"] for step in telemetry_window]
    error1 = [step["tank1"]["error"] for step in telemetry_window]
    error2 = [step["tank2"]["error"] for step in telemetry_window]

    def count_consecutive_above(values, threshold):
        best = 0
        cur = 0
        for v in values:
            if v > threshold:
                cur += 1
                if cur > best:
                    best = cur
            else:
                cur = 0
        return best

    # Tank1 loop drives pump2; a tank1 leak raises pump2 effort and error.
    # Healthy settled effort ranges up to 10.54 V for tank1, so require > 10.0 V.
    # Healthy settled |error| max 0.0736, so require > 0.09.
    # Start-up has effort up to 10.59 V but |error| above 0.09 only before
    # effort reaches 10.0, so no false positive.
    t1_high_effort = count_consecutive_above(effort1, 10.0)
    t1_high_error = count_consecutive_above([abs(e) for e in error1], 0.09)
    tank1_anomaly = t1_high_effort >= 3 and t1_high_error >= 3

    # Tank2 loop drives pump1; a tank2 leak raises pump1 effort and error.
    # Healthy settled effort max 9.26 V, so require > 9.3 V.
    # Healthy settled |error| max 0.0495, so require > 0.06.
    t2_high_effort = count_consecutive_above(effort2, 9.3)
    t2_high_error = count_consecutive_above([abs(e) for e in error2], 0.06)
    tank2_anomaly = t2_high_effort >= 3 and t2_high_error >= 3

    # Calm detection for restoration: loop effort comfortably near nominal and
    # error small; requires 10 consecutive samples to avoid restoring during
    # the start-up transient or a brief lull in a fault.
    t1_calm = count_consecutive_above([10.0 - e for e in effort1], 0.0) >= 10 and \
              count_consecutive_above([0.04 - abs(e) for e in error1], 0.0) >= 10
    t2_calm = count_consecutive_above([9.5 - e for e in effort2], 0.0) >= 10 and \
              count_consecutive_above([0.04 - abs(e) for e in error2], 0.0) >= 10

    LOWER_STEP = 0.02
    RESTORE_STEP = 0.01

    def next_setpoint(sp, nom, anomaly, calm):
        if anomaly:
            return max(0.05, sp - LOWER_STEP)
        if calm and sp < nom:
            return min(nom, sp + RESTORE_STEP)
        return sp

    new_sp1 = next_setpoint(active_setpoints["tank1"], nominal_targets["tank1"], tank1_anomaly, t1_calm)
    new_sp2 = next_setpoint(active_setpoints["tank2"], nominal_targets["tank2"], tank2_anomaly, t2_calm)

    return {
        "diagnosis": f"tank1 anomaly={tank1_anomaly}; tank2 anomaly={tank2_anomaly}",
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
