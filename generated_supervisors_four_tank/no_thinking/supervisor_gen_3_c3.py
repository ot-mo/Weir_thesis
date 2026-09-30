def supervise(telemetry_window, active_setpoints, nominal_targets):
    """Supervisory level-setpoint and anomaly-flag controller for the
    quadruple-tank process.  Pure function of its three arguments."""
    n = len(telemetry_window)
    m = 15
    tail = telemetry_window[-m:] if n >= m else telemetry_window

    def mean(vals):
        return sum(vals) / len(vals) if vals else 0.0

    e1 = mean([s["tank1"]["error"] for s in tail])
    e2 = mean([s["tank2"]["error"] for s in tail])
    f1 = mean([s["tank1"]["pump_effort"] for s in tail])
    f2 = mean([s["tank2"]["pump_effort"] for s in tail])
    peak1 = max([s["tank1"]["pump_effort"] for s in tail])
    peak2 = max([s["tank2"]["pump_effort"] for s in tail])

    err_gate = 0.075
    flag1 = (e1 >= err_gate and f1 >= 10.9 and peak1 >= 11.3)
    flag2 = (e2 >= err_gate and f2 >= 10.0 and peak2 >= 10.6)

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    STEP = 0.01
    healthy1 = (e1 < 0.045 and f1 < 10.4)
    healthy2 = (e2 < 0.045 and f2 < 9.5)

    if flag1:
        new_sp1 = max(0.05, sp1 - STEP)
    elif healthy1 and sp1 < nom1:
        new_sp1 = min(nom1, round(sp1 + STEP, 4))
    else:
        new_sp1 = sp1

    if flag2:
        new_sp2 = max(0.05, sp2 - STEP)
    elif healthy2 and sp2 < nom2:
        new_sp2 = min(nom2, round(sp2 + STEP, 4))
    else:
        new_sp2 = sp2

    return {
        "diagnosis": "leak flag tank1=%s (e=%.3f,f=%.2f,pk=%.2f); tank2=%s (e=%.3f,f=%.2f,pk=%.2f)"
                     % (flag1, e1, f1, peak1, flag2, e2, f2, peak2),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": flag1, "tank2": flag2},
    }
