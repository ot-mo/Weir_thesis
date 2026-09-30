def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    if n == 0:
        return {
            "diagnosis": "empty window",
            "adjusted_setpoints": {"tank1": active_setpoints["tank1"], "tank2": active_setpoints["tank2"]},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    last = telemetry_window[-1]

    def mean_recent(vals, k):
        m = vals[-k:] if len(vals) >= k else vals
        if not m:
            return 0.0
        return sum(m) / float(len(m))

    eff1 = [s["tank1"]["pump_effort"] for s in telemetry_window]
    eff2 = [s["tank2"]["pump_effort"] for s in telemetry_window]
    lvl1 = [s["tank1"]["level"] for s in telemetry_window]
    lvl2 = [s["tank2"]["level"] for s in telemetry_window]

    eff1_m = mean_recent(eff1, 10)
    eff2_m = mean_recent(eff2, 10)

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    # Healthy settled effort envelope (from reference stats).
    BASE_EFF1 = 9.35
    BASE_EFF2 = 8.96

    # Setpoint trim reduces required effort roughly proportionally to sqrt(h).
    trim1 = 0.0
    if nom1 > 1e-6:
        ratio1 = sp1 / nom1
        if ratio1 < 0.0:
            ratio1 = 0.0
        trim1 = 1.0 - (ratio1 ** 0.5)
    trim2 = 0.0
    if nom2 > 1e-6:
        ratio2 = sp2 / nom2
        if ratio2 < 0.0:
            ratio2 = 0.0
        trim2 = 1.0 - (ratio2 ** 0.5)

    # Expected healthy effort at the current (possibly trimmed) setpoint.
    exp_eff1 = BASE_EFF1 * (1.0 - 0.55 * trim1)
    exp_eff2 = BASE_EFF2 * (1.0 - 0.55 * trim2)

    # Level deficits relative to the ACTIVE setpoint (mean over 10 s to be robust).
    def mean_deficit(sp, levels):
        m = levels[-10:] if len(levels) >= 10 else levels
        if not m:
            return 0.0
        s = 0.0
        for v in m:
            s += (sp - v)
        return s / float(len(m))

    def1 = mean_deficit(sp1, lvl1)
    def2 = mean_deficit(sp2, lvl2)

    # Thresholds: sustained genuine leak drives loop effort well above healthy envelope.
    E1_HI = 1.10
    E1_HI_EXTREME = 11.3
    E2_HI = 0.85
    E2_HI_EXTREME = 9.85

    D1_HI = 0.06
    D2_HI = 0.05
    D_CLEAR = 0.03

    # Rolling streaks of the enter/clear condition over the window (10 calls max).
    def streak_above_eff(vals, base_thresh, extreme_thresh, defi, def_thresh):
        cnt = 0
        m = vals[-10:] if len(vals) >= 10 else vals
        for v in reversed(m):
            if (v > base_thresh) or (v > extreme_thresh):
                cnt += 1
            else:
                break
        return cnt

    # Use per-sample effort but require the mean deficit across full window.
    enter_streak1 = 0
    for v in reversed(eff1[-10:] if len(eff1) >= 10 else eff1):
        if v > (exp_eff1 + E1_HI):
            enter_streak1 += 1
        else:
            break
    enter_streak1_extreme = 0
    for v in reversed(eff1[-10:] if len(eff1) >= 10 else eff1):
        if v > E1_HI_EXTREME:
            enter_streak1_extreme += 1
        else:
            break

    enter_streak2 = 0
    for v in reversed(eff2[-10:] if len(eff2) >= 10 else eff2):
        if v > (exp_eff2 + E2_HI):
            enter_streak2 += 1
        else:
            break
    enter_streak2_extreme = 0
    for v in reversed(eff2[-10:] if len(eff2) >= 10 else eff2):
        if v > E2_HI_EXTREME:
            enter_streak2 += 1
        else:
            break

    # Clear conditions: both effort back near healthy expectation AND deficit small.
    def clear_streak(vals, expected, defi, def_thresh):
        cnt = 0
        m = vals[-10:] if len(vals) >= 10 else vals
        for v in reversed(m):
            if v < (expected + 0.45):
                cnt += 1
            else:
                break
        if cnt >= 4 and defi < def_thresh:
            return cnt
        return cnt  # streak of effort-clear alone; combine with deficit below

    clear_eff1 = 0
    for v in reversed(eff1[-10:] if len(eff1) >= 10 else eff1):
        if v < (exp_eff1 + 0.45):
            clear_eff1 += 1
        else:
            break

    clear_eff2 = 0
    for v in reversed(eff2[-10:] if len(eff2) >= 10 else eff2):
        if v < (exp_eff2 + 0.40):
            clear_eff2 += 1
        else:
            break

    enter1 = ((enter_streak1 >= 3) and (def1 > D1_HI)) or (enter_streak1_extreme >= 6)
    enter2 = ((enter_streak2 >= 3) and (def2 > D2_HI)) or (enter_streak2_extreme >= 6)

    clear1 = (clear_eff1 >= 4) and (def1 < D_CLEAR) and (eff1_m < (exp_eff1 + 0.45))
    clear2 = (clear_eff2 >= 4) and (def2 < D_CLEAR) and (eff2_m < (exp_eff2 + 0.40))

    tank1_anomaly = False
    tank2_anomaly = False

    # Hysteresis: if setpoint already trimmed, keep flag until genuinely cleared.
    if sp1 < nom1 - 1e-9:
        tank1_anomaly = not clear1
    elif enter1:
        tank1_anomaly = True
    else:
        tank1_anomaly = False

    if sp2 < nom2 - 1e-9:
        tank2_anomaly = not clear2
    elif enter2:
        tank2_anomaly = True
    else:
        tank2_anomaly = False

    LOWER_STEP = 0.010
    RESTORE_STEP = 0.005

    if tank1_anomaly:
        new_sp1 = max(0.05, sp1 - LOWER_STEP)
    elif sp1 < nom1:
        new_sp1 = min(nom1, sp1 + RESTORE_STEP)
    else:
        new_sp1 = sp1

    if tank2_anomaly:
        new_sp2 = max(0.05, sp2 - LOWER_STEP)
    elif sp2 < nom2:
        new_sp2 = min(nom2, sp2 + RESTORE_STEP)
    else:
        new_sp2 = sp2

    return {
        "diagnosis": "t1=%s (eff=%.2f exp=%.2f def=%.3f); t2=%s (eff=%.2f exp=%.2f def=%.3f)" % (
            tank1_anomaly, eff1_m, exp_eff1, def1, tank2_anomaly, eff2_m, exp_eff2, def2),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
