def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    if n == 0:
        return {
            "diagnosis": "empty telemetry window; holding setpoints, no flags",
            "adjusted_setpoints": {
                "tank1": active_setpoints.get("tank1", nominal_targets.get("tank1", 0.30)),
                "tank2": active_setpoints.get("tank2", nominal_targets.get("tank2", 0.35)),
            },
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    eff1 = [step["tank1"]["pump_effort"] for step in telemetry_window]
    eff2 = [step["tank2"]["pump_effort"] for step in telemetry_window]
    lvl1 = [step["tank1"]["level"] for step in telemetry_window]
    lvl2 = [step["tank2"]["level"] for step in telemetry_window]

    # Absolute "pump rail" thresholds from the fault-free reference statistics:
    #   loop1 (tank1.pump_effort = pump 2) healthy max 10.59 V (start-up), 10.54 V (settled)
    #   loop2 (tank2.pump_effort = pump 1) healthy max  8.76 V (start-up),  9.26 V (settled)
    # A leak drives the tank's OWN off-diagonally paired loop onto the 12 V limit,
    # so an absolute rail test is safe and the old effort-ratio test is not used.
    EFF1_TH = 11.0
    EFF2_TH = 9.8
    # Level recovery gate: fault-free slope ~0, active-leak plateau ~0, recovery ~+0.04 m/10 s.
    RISE_TH = 0.015

    def detect(eff, lvl, eff_th):
        recent = eff[-5:] if len(eff) >= 5 else eff
        eff_high = max(recent) > eff_th
        if len(lvl) >= 11:
            rise = lvl[-1] - lvl[-11]
        else:
            rise = lvl[-1] - lvl[0]
        recovering = rise > RISE_TH
        # Leak => loop railed and level flat/falling.  Release only after the
        # level itself has climbed, because the loop stays railed while refilling.
        return eff_high and (not recovering)

    tank1_anomaly = detect(eff1, lvl1, EFF1_TH)
    tank2_anomaly = detect(eff2, lvl2, EFF2_TH)

    def next_sp(sp, nom, anomaly):
        if anomaly:
            floor_sp = max(0.05, nom - 0.05)
            if sp > floor_sp:
                return max(floor_sp, sp - 0.01)
            return sp
        if sp < nom:
            return min(nom, sp + 0.01)
        if sp > nom:
            return max(nom, sp - 0.01)
        return sp

    sp1 = next_sp(active_setpoints["tank1"], nominal_targets["tank1"], tank1_anomaly)
    sp2 = next_sp(active_setpoints["tank2"], nominal_targets["tank2"], tank2_anomaly)

    return {
        "diagnosis": "tank1 leak-suspect=%s; tank2 leak-suspect=%s" % (tank1_anomaly, tank2_anomaly),
        "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
