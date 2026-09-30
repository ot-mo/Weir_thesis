def supervise(telemetry_window, active_setpoints, nominal_targets):
    EFF_HIGH = {"tank1": 11.0, "tank2": 9.8}
    EFF_LOW = {"tank1": 9.5, "tank2": 8.0}
    ERR_HIGH = {"tank1": 0.08, "tank2": 0.06}
    DELTA_ERR_SMALL = 0.005
    RECOVERY_DELTA = -0.002

    def detect(tank):
        n = len(telemetry_window)
        if n == 0:
            return False
        efforts = [s[tank]["pump_effort"] for s in telemetry_window]
        errs = [s[tank]["error"] for s in telemetry_window]
        if n >= 10:
            eff_max = max(efforts[-10:])
        else:
            eff_max = max(efforts)
        if n >= 11:
            delta_err = errs[-1] - errs[-11]
        else:
            delta_err = errs[-1] - errs[0]
        if eff_max > EFF_HIGH[tank] and delta_err > RECOVERY_DELTA:
            return True
        if eff_max > EFF_LOW[tank] and delta_err > DELTA_ERR_SMALL and errs[-1] > ERR_HIGH[tank]:
            return True
        return False

    a1 = detect("tank1")
    a2 = detect("tank2")

    return {
        "diagnosis": "tank1 anomaly=" + str(a1) + "; tank2 anomaly=" + str(a2),
        "adjusted_setpoints": {
            "tank1": float(nominal_targets["tank1"]),
            "tank2": float(nominal_targets["tank2"]),
        },
        "anomaly_flags": {"tank1": bool(a1), "tank2": bool(a2)},
    }
