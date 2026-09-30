def supervise(telemetry_window, active_setpoints, nominal_targets):
    def stat(vals):
        n = len(vals)
        if n == 0:
            return 0.0
        return sum(vals) / n

    def median(vals):
        sv = sorted(vals)
        m = len(sv)
        if m == 0:
            return 0.0
        if m % 2 == 1:
            return sv[m // 2]
        return (sv[m // 2 - 1] + sv[m // 2]) / 2.0

    def leak_test(levels, errors, efforts):
        n = len(levels)
        if n < 6:
            return False, False
        mean_err = stat(errors)
        win_max = max(levels)
        win_min = min(levels)
        net_drop = levels[0] - levels[-1]
        down_steps = 0
        run = 0
        for i in range(1, n):
            if levels[i] - levels[i - 1] < -0.003:
                run += 1
                if run > down_steps:
                    down_steps = run
            else:
                run = 0
        falling = net_drop > 0.08 and win_min < 0.65 * win_max and down_steps >= 3
        slow_leak = falling and mean_err >= 0.05
        half = max(3, n // 2)
        early = median(efforts[:half])
        late = median(efforts[-half:])
        ratio = late / early if early > 1.0 else 1.0
        working = mean_err >= 0.04 and ratio >= 1.35 and late < 11.0
        anomaly = slow_leak or working
        calm = mean_err < 0.04 and not falling
        return anomaly, calm

    levels1 = [step["tank1"]["level"] for step in telemetry_window]
    levels2 = [step["tank2"]["level"] for step in telemetry_window]
    errors1 = [step["tank1"]["error"] for step in telemetry_window]
    errors2 = [step["tank2"]["error"] for step in telemetry_window]
    efforts1 = [step["tank1"]["pump_effort"] for step in telemetry_window]
    efforts2 = [step["tank2"]["pump_effort"] for step in telemetry_window]

    tank1_anomaly, tank1_calm = leak_test(levels1, errors1, efforts1)
    tank2_anomaly, tank2_calm = leak_test(levels2, errors2, efforts2)

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
        "diagnosis": "tank1 anomaly=%s; tank2 anomaly=%s" % (tank1_anomaly, tank2_anomaly),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
