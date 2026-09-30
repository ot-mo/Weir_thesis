def supervise(telemetry_window, active_setpoints, nominal_targets):
    HIGH1 = 11.0
    HIGH2 = 11.0
    CLEAR1 = 10.5
    CLEAR2 = 9.3
    LEVEL_GAP = 0.01

    n = len(telemetry_window)
    eff1 = [s["tank1"]["pump_effort"] for s in telemetry_window]
    eff2 = [s["tank2"]["pump_effort"] for s in telemetry_window]
    lvl1 = [s["tank1"]["level"] for s in telemetry_window]
    lvl2 = [s["tank2"]["level"] for s in telemetry_window]

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    def recent(vals, k):
        if n == 0:
            return []
        kk = min(k, n)
        return vals[n - kk:]

    def streak_high(vals, levels, target, high_thr, floor_thr, need_high, need_low, gap):
        # returns (is_high_streak, is_low_streak) over the window tail
        h = 0
        l = 0
        best_h = 0
        best_l = 0
        for i in range(n):
            if vals[i] >= high_thr and (target - levels[i]) >= gap:
                h += 1
                best_h = max(best_h, h)
            else:
                h = 0
            if vals[i] <= floor_thr:
                l += 1
                best_l = max(best_l, l)
            else:
                l = 0
        return best_h >= need_high, best_l >= need_low

    h1_high, h1_low = streak_high(eff1, lvl1, sp1, HIGH1, CLEAR1, 2, 3, LEVEL_GAP)
    h2_high, h2_low = streak_high(eff2, lvl2, sp2, HIGH2, CLEAR2, 2, 3, LEVEL_GAP)

    tank1_anomaly = h1_high
    tank2_anomaly = h2_high

    LOWER_STEP = 0.02

    if tank1_anomaly:
        new_sp1 = max(0.05, sp1 - LOWER_STEP)
    elif h1_low and sp1 < nom1:
        new_sp1 = nom1
    else:
        new_sp1 = sp1

    if tank2_anomaly:
        new_sp2 = max(0.05, sp2 - LOWER_STEP)
    elif h2_low and sp2 < nom2:
        new_sp2 = nom2
    else:
        new_sp2 = sp2

    return {
        "diagnosis": "tank1 anomaly=%s; tank2 anomaly=%s" % (tank1_anomaly, tank2_anomaly),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
