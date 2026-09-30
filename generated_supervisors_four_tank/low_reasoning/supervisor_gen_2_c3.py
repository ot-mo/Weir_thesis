def supervise(telemetry_window, active_setpoints, nominal_targets):
    EFF_HIGH_T1 = 10.8
    EFF_HIGH_T2 = 9.8
    EFF_LOW_T1 = 9.5
    EFF_LOW_T2 = 8.0
    ERROR_SLOPE_THRESH = 0.002
    RECOVERY_ERROR_SLOPE = -0.00005
    RECOVERY_ERROR_MIN = 0.015

    def med(vals):
        sv = sorted(vals)
        m = len(sv)
        if m == 0:
            return 0.0
        if m % 2 == 1:
            return sv[m // 2]
        return 0.5 * (sv[m // 2 - 1] + sv[m // 2])

    def detect(tank, effort_high, effort_low):
        levels = [s[tank]["level"] for s in telemetry_window]
        efforts = [s[tank]["pump_effort"] for s in telemetry_window]
        errors = [s[tank]["error"] for s in telemetry_window]
        n = len(efforts)
        if n < 10:
            return False
        recent_eff = efforts[-10:]
        med_eff = med(recent_eff)
        err_slope = (errors[-1] - errors[-10]) / 9.0
        err_now = errors[-1]
        if med_eff > effort_high:
            if err_now > RECOVERY_ERROR_MIN and err_slope < RECOVERY_ERROR_SLOPE:
                return False
            return True
        if err_slope > ERROR_SLOPE_THRESH and err_now > 0.04 and med_eff > effort_low:
            return True
        return False

    a1 = detect("tank1", EFF_HIGH_T1, EFF_LOW_T1)
    a2 = detect("tank2", EFF_HIGH_T2, EFF_LOW_T2)

    return {
        "diagnosis": "tank1 anomaly=" + str(a1) + "; tank2 anomaly=" + str(a2),
        "adjusted_setpoints": {
            "tank1": float(nominal_targets["tank1"]),
            "tank2": float(nominal_targets["tank2"]),
        },
        "anomaly_flags": {"tank1": bool(a1), "tank2": bool(a2)},
    }