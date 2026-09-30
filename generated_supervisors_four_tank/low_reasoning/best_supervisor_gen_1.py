def supervise(telemetry_window, active_setpoints, nominal_targets):
    EFF_FAST = 11.2
    EFF_MED = 10.9
    RECOVERY_SLOPE = 0.0015

    def med(vals):
        sv = sorted(vals)
        m = len(sv)
        if m == 0:
            return 0.0
        if m % 2 == 1:
            return sv[m // 2]
        return 0.5 * (sv[m // 2 - 1] + sv[m // 2])

    def detect(levels, efforts):
        if len(efforts) == 0:
            return False
        fast = max(efforts[-8:])
        slow = med(efforts[-20:])
        if not (fast > EFF_FAST or slow > EFF_MED):
            return False
        k = min(10, len(levels))
        if k > 1:
            slope = (levels[-1] - levels[-k]) / float(k - 1)
            if slope > RECOVERY_SLOPE:
                return False
        return True

    levels1 = [s["tank1"]["level"] for s in telemetry_window]
    levels2 = [s["tank2"]["level"] for s in telemetry_window]
    efforts1 = [s["tank1"]["pump_effort"] for s in telemetry_window]
    efforts2 = [s["tank2"]["pump_effort"] for s in telemetry_window]

    a1 = detect(levels1, efforts1)
    a2 = detect(levels2, efforts2)

    return {
        "diagnosis": "tank1 anomaly=" + str(a1) + "; tank2 anomaly=" + str(a2),
        "adjusted_setpoints": {
            "tank1": float(nominal_targets["tank1"]),
            "tank2": float(nominal_targets["tank2"]),
        },
        "anomaly_flags": {"tank1": bool(a1), "tank2": bool(a2)},
    }
