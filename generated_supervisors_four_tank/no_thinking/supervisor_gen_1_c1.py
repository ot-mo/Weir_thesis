def supervise(telemetry_window, active_setpoints, nominal_targets):
    # Physics: off-diagonal pairing means tankN.level is regulated by
    # tankN.pump_effort.  A leak in tankN increases its outflow; the loop
    # regulating tankN lifts tankN.pump_effort until it rails at 12 V.
    # At the same time the leaking tank's level falls below the window start.
    # Therefore key on (effort saturated) AND (level dropped) rather than
    # on an effort ratio that a saturated pump makes constant.

    def mean_effort(win, tank):
        vals = [s[tank]["pump_effort"] for s in win]
        return sum(vals) / float(len(vals))

    def level_trend(win, tank):
        lv = [s[tank]["level"] for s in win]
        n = len(lv)
        # first quarter vs last quarter, robust to a single noisy sample
        q = max(1, n // 4)
        first = sum(lv[:q]) / float(q)
        last = sum(lv[-q:]) / float(q)
        return first, last

    # Thresholds: EffortHi=11.5 V is above every healthy effort maximum seen
    # in telemetry (start-up maxes 10.59 / 8.76, settled maxes 10.54 / 9.26)
    # while a leaking loop in the traces sits at 12.0 V.  LEVEL_DROP=0.03 m is
    # below the smallest significant leak drop but above measurement noise
    # (levels are rounded to 0.1 mm).
    EFFORT_HI = 11.5
    LEVEL_DROP = 0.03

    tank1_eff = mean_effort(telemetry_window, "tank1")
    tank2_eff = mean_effort(telemetry_window, "tank2")
    f1, l1 = level_trend(telemetry_window, "tank1")
    f2, l2 = level_trend(telemetry_window, "tank2")

    tank1_high_effort = tank1_eff > EFFORT_HI
    tank2_high_effort = tank2_eff > EFFORT_HI
    tank1_dropping = (f1 - l1) > LEVEL_DROP
    tank2_dropping = (f2 - l2) > LEVEL_DROP

    tank1_anomaly = tank1_high_effort and tank1_dropping
    tank2_anomaly = tank2_high_effort and tank2_dropping

    # A loop is "calm" only when it is neither saturated nor dropping: that
    # is the condition under which its fault has genuinely cleared and its
    # setpoint may be restored toward nominal.
    tank1_calm = (not tank1_high_effort) and (not tank1_dropping)
    tank2_calm = (not tank2_high_effort) and (not tank2_dropping)

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
        "diagnosis": (
            "tank1 anomaly=%s (eff=%.2f drop=%.3f); tank2 anomaly=%s (eff=%.2f drop=%.3f)"
            % (tank1_anomaly, tank1_eff, f1 - l1, tank2_anomaly, tank2_eff, f2 - l2)
        ),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": bool(tank1_anomaly), "tank2": bool(tank2_anomaly)},
    }
