def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    last = telemetry_window[-1] if n > 0 else None

    def mean(vals, k):
        if not vals:
            return 0.0
        m = vals[-k:] if len(vals) >= k else vals
        return sum(m) / float(len(m))

    if last is None:
        return {
            "diagnosis": "empty window",
            "adjusted_setpoints": {"tank1": active_setpoints["tank1"], "tank2": active_setpoints["tank2"]},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    eff1_series = [s["tank1"]["pump_effort"] for s in telemetry_window]
    eff2_series = [s["tank2"]["pump_effort"] for s in telemetry_window]
    err1_series = [s["tank1"]["error"] for s in telemetry_window]
    err2_series = [s["tank2"]["error"] for s in telemetry_window]
    lvl1 = last["tank1"]["level"]
    lvl2 = last["tank2"]["level"]

    eff1_mean = mean(eff1_series, 7)
    eff2_mean = mean(eff2_series, 7)
    err1_mean = mean(err1_series, 5)
    err2_mean = mean(err2_series, 5)

    # Start-up detection: first sample level below 0.22 m indicates transient phase.
    start_level = telemetry_window[0]["tank1"]["level"]
    start_up = start_level < 0.22

    # Error gate: start-up transients require a higher gate to avoid false positives.
    ERR_GATE1 = 0.09 if start_up else 0.055
    ERR_GATE2 = 0.09 if start_up else 0.055

    # Effort thresholds above healthy settled means (tank1 9.35 V, tank2 8.96 V).
    EFF1_ENTER = 10.9
    EFF2_ENTER = 9.45
    EFF1_EXIT = 10.4
    EFF2_EXIT = 9.10

    # 7-sample vote: at least 5 samples above effort threshold.
    def vote(effs, errs, eff_th, err_th):
        ec = 0
        for v in effs[-7:]:
            if v > eff_th:
                ec += 1
        xc = 0
        for e in errs[-7:]:
            if e > err_th:
                xc += 1
        return (ec >= 5) and (xc >= 3)

    def vote_exit(effs, errs, eff_th, err_th):
        for v in effs[-7:]:
            if v > eff_th:
                return False
        for e in errs[-7:]:
            if e > err_th:
                return False
        return True

    enter1 = vote(eff1_series, err1_series, EFF1_ENTER, ERR_GATE1)
    enter2 = vote(eff2_series, err2_series, EFF2_ENTER, ERR_GATE2)
    clear1 = vote_exit(eff1_series, err1_series, EFF1_EXIT, ERR_GATE1)
    clear2 = vote_exit(eff2_series, err2_series, EFF2_EXIT, ERR_GATE2)

    # Hysteresis: once a setpoint has been trimmed below nominal, hold the flag
    # until effort and error are both clearly low, to prevent chatter inside the
    # true fault interval.
    trimmed1 = sp1 < nom1 - 1e-9
    trimmed2 = sp2 < nom2 - 1e-9

    if trimmed1:
        tank1_anomaly = not clear1
    elif enter1:
        tank1_anomaly = True
    else:
        tank1_anomaly = False

    if trimmed2:
        tank2_anomaly = not clear2
    elif enter2:
        tank2_anomaly = True
    else:
        tank2_anomaly = False

    # If tank2 effort is clearly high, it may be compensating for a tank1 leak;
    # only allow tank2 flag if its own level also lags. Conversely, tank1 flag
    # requires effort on its own loop.
    if tank2_anomaly and not (eff2_mean > EFF2_ENTER):
        tank2_anomaly = False
    if tank1_anomaly and not (eff1_mean > EFF1_ENTER):
        tank1_anomaly = False

    LOWER_STEP = 0.015
    RESTORE_STEP = 0.008

    if tank1_anomaly:
        new_sp1 = max(0.05, sp1 - LOWER_STEP) if sp1 > 0.05 else sp1
    elif sp1 < nom1 and not (tank1_anomaly or tank2_anomaly):
        new_sp1 = min(nom1, sp1 + RESTORE_STEP)
    else:
        new_sp1 = sp1

    if tank2_anomaly:
        new_sp2 = max(0.05, sp2 - LOWER_STEP) if sp2 > 0.05 else sp2
    elif sp2 < nom2 and not (tank1_anomaly or tank2_anomaly):
        new_sp2 = min(nom2, sp2 + RESTORE_STEP)
    else:
        new_sp2 = sp2

    return {
        "diagnosis": "t1=%s(eff%.2f err%.3f) t2=%s(eff%.2f err%.3f)" % (
            tank1_anomaly, eff1_mean, err1_mean, tank2_anomaly, eff2_mean, err2_mean),
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
