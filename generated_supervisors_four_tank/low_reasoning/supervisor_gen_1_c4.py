def supervise(telemetry_window, active_setpoints, nominal_targets):
    lv1 = [s["tank1"]["level"] for s in telemetry_window]
    lv2 = [s["tank2"]["level"] for s in telemetry_window]
    ef1 = [s["tank1"]["pump_effort"] for s in telemetry_window]
    ef2 = [s["tank2"]["pump_effort"] for s in telemetry_window]
    er1 = [s["tank1"]["error"] for s in telemetry_window]
    er2 = [s["tank2"]["error"] for s in telemetry_window]

    def mean(v):
        return sum(v) / float(len(v)) if v else 0.0

    # Absolute, physics-anchored detection. Healthy pump effort peaks at
    # 10.59 V (start-up) / 10.54 V (settled) for tank1 and 8.76 / 9.26 V for
    # tank2; a leaking lower tank drives its own loop (the OPPOSITE pump) into
    # the 12 V saturation ceiling, which no healthy window can reach.
    SAT_V = 11.0
    FALL_EFF = 9.5
    FALL_M = 0.012
    ERR_M = 0.10
    ERR_EFF = 10.0

    def detect(level, effort, error):
        eff_recent = mean(effort[-10:])
        err_recent = mean([abs(x) for x in error[-10:]])
        lvl_recent = mean(level[-10:])
        lvl_prev = mean(level[-20:-10])
        drop = lvl_prev - lvl_recent  # positive => level is falling
        saturated = eff_recent >= SAT_V
        falling = (drop > FALL_M) and (eff_recent >= FALL_EFF)
        big_err = (err_recent > ERR_M) and (eff_recent >= ERR_EFF) and (drop > -0.004)
        return (saturated or falling or big_err), lvl_recent

    a1, lvl1 = detect(lv1, ef1, er1)
    a2, lvl2 = detect(lv2, ef2, er2)

    def next_sp(sp, nom, anomaly, level):
        if anomaly:
            cand = sp - 0.02
            # never lower below level+0.05: keeps error positive so the loop
            # stays driven and the tank cannot be pushed toward the 0.02 m
            # safety limit by our own setpoint action.
            if cand >= level + 0.05 and cand >= 0.05:
                return cand
            return sp
        if sp < nom:
            return min(nom, sp + 0.05)
        return sp

    sp1 = next_sp(active_setpoints["tank1"], nominal_targets["tank1"], a1, lvl1)
    sp2 = next_sp(active_setpoints["tank2"], nominal_targets["tank2"], a2, lvl2)

    return {
        "diagnosis": "tank1 anomaly=%s; tank2 anomaly=%s (saturation/level-drop/error detector)" % (a1, a2),
        "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
        "anomaly_flags": {"tank1": a1, "tank2": a2},
    }
