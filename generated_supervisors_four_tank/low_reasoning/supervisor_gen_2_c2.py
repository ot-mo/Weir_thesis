def supervise(telemetry_window, active_setpoints, nominal_targets):
    # Thresholds derived from healthy reference statistics:
    # Tank1: healthy max effort ~10.59 (start-up), ~10.54 (settled); max error settled ~0.0736
    # Tank2: healthy max effort ~8.76 (start-up), ~9.26 (settled); max error settled ~0.0495
    EFF_HIGH_T1 = 11.0
    EFF_MED_T1 = 10.0
    ERR_MED_T1 = 0.08
    EFF_HIGH_T2 = 10.0
    EFF_MED_T2 = 8.9
    ERR_MED_T2 = 0.06
    JUMP_THRESH = 1.0
    SLOPE_THRESH = 0.0005  # m/s, above this indicates recovery

    def analyze_tank(levels, efforts, errors, eff_high, eff_med, err_med):
        n = len(levels)
        if n < 20:
            return False
        recent_levels = levels[-10:]
        recent_efforts = efforts[-10:]
        recent_errors = errors[-10:]
        prev_efforts = efforts[-20:-10]
        effort_max = max(recent_efforts)
        level_slope = (recent_levels[-1] - recent_levels[0]) / 9.0
        error_mean = sum(recent_errors) / 10.0
        if len(prev_efforts) > 0:
            prev_max = max(prev_efforts)
            effort_jump = effort_max - prev_max
        else:
            effort_jump = 0.0

        if effort_max > eff_high and level_slope < SLOPE_THRESH:
            return True
        if effort_max > eff_med and level_slope < SLOPE_THRESH and error_mean > err_med:
            return True
        if effort_jump > JUMP_THRESH and effort_max > eff_med and level_slope < SLOPE_THRESH:
            return True
        return False

    levels1 = [s["tank1"]["level"] for s in telemetry_window]
    efforts1 = [s["tank1"]["pump_effort"] for s in telemetry_window]
    errors1 = [s["tank1"]["error"] for s in telemetry_window]
    levels2 = [s["tank2"]["level"] for s in telemetry_window]
    efforts2 = [s["tank2"]["pump_effort"] for s in telemetry_window]
    errors2 = [s["tank2"]["error"] for s in telemetry_window]

    a1 = analyze_tank(levels1, efforts1, errors1, EFF_HIGH_T1, EFF_MED_T1, ERR_MED_T1)
    a2 = analyze_tank(levels2, efforts2, errors2, EFF_HIGH_T2, EFF_MED_T2, ERR_MED_T2)

    return {
        "diagnosis": "tank1 anomaly=" + str(a1) + "; tank2 anomaly=" + str(a2),
        "adjusted_setpoints": {
            "tank1": float(nominal_targets["tank1"]),
            "tank2": float(nominal_targets["tank2"]),
        },
        "anomaly_flags": {"tank1": bool(a1), "tank2": bool(a2)},
    }
