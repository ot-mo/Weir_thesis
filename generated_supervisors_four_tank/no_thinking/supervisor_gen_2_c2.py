def supervise(telemetry_window, active_setpoints, nominal_targets):
    effort1 = [step["tank1"]["pump_effort"] for step in telemetry_window]
    effort2 = [step["tank2"]["pump_effort"] for step in telemetry_window]
    level1 = [step["tank1"]["level"] for step in telemetry_window]
    level2 = [step["tank2"]["level"] for step in telemetry_window]

    n = len(level1)
    last = max(1, min(10, n))

    def mean(vals):
        return sum(vals) / len(vals)

    eff1_now = mean(effort1[-last:])
    eff2_now = mean(effort2[-last:])
    lvl1 = level1[-1]
    lvl2 = level2[-1]

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    # A lower-tank leak saturates that tank's own PI loop at the 12 V pump limit
    # and drives the level well below its (possibly already lowered) setpoint.
    # Healthy effort never exceeds 10.59 V in start-up or 10.54 V settled, so a
    # 11.6 V mean plus 0.015 m droop cannot false-positive on a healthy plant.
    SAT_EFFORT = 11.6
    DROOP = 0.015

    sat1 = eff1_now >= SAT_EFFORT
    sat2 = eff2_now >= SAT_EFFORT

    sig1 = sat1 and (sp1 - lvl1) > DROOP
    sig2 = sat2 and (sp2 - lvl2) > DROOP

    # Detect sustained saturation over the most recent portion of the window
    # (previous call's flag is not available; stateless, so use the window).
    def sustained(effort):
        if n < 12:
            return False
        tail = effort[-last:]
        prev = effort[-2 * last:-last]
        return mean(tail) >= SAT_EFFORT and mean(prev) >= SAT_EFFORT

    pers1 = sustained(effort1)
    pers2 = sustained(effort2)

    tank1_anomaly = sig1 and pers1
    tank2_anomaly = sig2 and pers2

    # Calm/clear test: no saturation recently and level tracking the active
    # setpoint closely => the fault has genuinely cleared.
    def clear_test(effort, lvl, sp):
        if n < 12:
            return False
        if mean(effort[-last:]) >= SAT_EFFORT:
            return False
        if mean(effort[-2 * last:-last]) >= SAT_EFFORT:
            return False
        return abs(sp - lvl) < 0.01

    calm1 = clear_test(effort1, lvl1, sp1)
    calm2 = clear_test(effort2, lvl2, sp2)

    LOWER_STEP = 0.02
    RESTORE_STEP = 0.015

    def next_setpoint(sp, nom, anomaly, calm):
        if anomaly:
            return max(0.05, sp - LOWER_STEP)
        if calm and sp < nom:
            return min(nom, sp + RESTORE_STEP)
        return sp

    new_sp1 = next_setpoint(sp1, nom1, tank1_anomaly, calm1)
    new_sp2 = next_setpoint(sp2, nom2, tank2_anomaly, calm2)

    return {
        "diagnosis": (
            "tank1: eff=%.2f lvl=%.3f sp=%.3f anomaly=%s; tank2: eff=%.2f lvl=%.3f sp=%.3f anomaly=%s"
            % (eff1_now, lvl1, sp1, tank1_anomaly, eff2_now, lvl2, sp2, tank2_anomaly)
        ),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
