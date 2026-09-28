def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---- external, fault-independent anchors (measured healthy episode) ----
    TOT_ANCHOR = 17.77      # mean(v1 + v2) [V]
    SPLIT_ANCHOR = 3.05     # mean(v1 - v2) [V]

    # healthy 50-sample block-mean total effort stays within ~2.5 V of the anchor
    DT_GATE = 3.0
    # a leak moves the split by 1/(1 - 2*gamma) = 1.667 x the total excess
    SHAPE_LO = 1.30
    SHAPE_HI = 2.60
    # block-mean |error|: healthy 0.074 (tank1) / 0.083 (tank2); fill ~0.25
    ERR_CAP = 0.16
    # recent-25-sample confirmation (same magnitude, relaxed shape)
    DT_GATE_REC = 2.4
    SHAPE_LO_REC = 1.10
    SHAPE_HI_REC = 3.00

    LOWER_STEP = 0.02
    RESTORE_STEP = 0.03

    n = len(telemetry_window)
    if n < 4:
        return {
            "diagnosis": "telemetry too short for a block decision",
            "adjusted_setpoints": {
                "tank1": active_setpoints["tank1"],
                "tank2": active_setpoints["tank2"],
            },
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    def block(lo, hi):
        cnt = hi - lo
        tot = 0.0
        spl = 0.0
        e1 = 0.0
        e2 = 0.0
        for i in range(lo, hi):
            s = telemetry_window[i]
            a = s["tank1"]["pump_effort"]
            b = s["tank2"]["pump_effort"]
            tot += a + b
            spl += a - b
            e1 += abs(s["tank1"]["error"])
            e2 += abs(s["tank2"]["error"])
        return tot / cnt, spl / cnt, e1 / cnt, e2 / cnt

    half = n // 2
    tot_a, spl_a, e1_a, e2_a = block(0, n)
    tot_r, spl_r, e1_r, e2_r = block(n - half, n)

    dT = tot_a - TOT_ANCHOR
    dS = spl_a - SPLIT_ANCHOR
    dTr = tot_r - TOT_ANCHOR
    dSr = spl_r - SPLIT_ANCHOR

    err_ok = bool(e1_a < ERR_CAP and e2_a < ERR_CAP)
    err_ok_r = bool(e1_r < ERR_CAP and e2_r < ERR_CAP)

    # tank-1 leak: total up, split pushed DOWN by ~1.667 x the total excess
    tank1_full = bool(err_ok and dT > DT_GATE
                      and dS <= -SHAPE_LO * dT and dS >= -SHAPE_HI * dT)
    # tank-2 leak: mirrored (reachable only below dT ~ 1.4 V by rail geometry)
    tank2_full = bool(err_ok and dT > DT_GATE
                      and dS >= SHAPE_LO * dT and dS <= SHAPE_HI * dT)
    tank1_rec = bool(err_ok_r and dTr > DT_GATE_REC
                     and dSr <= -SHAPE_LO_REC * dTr and dSr >= -SHAPE_HI_REC * dTr)
    tank2_rec = bool(err_ok_r and dTr > DT_GATE_REC
                     and dSr >= SHAPE_LO_REC * dTr and dSr <= SHAPE_HI_REC * dTr)

    tank1_anomaly = bool(tank1_full and tank1_rec)
    tank2_anomaly = bool(tank2_full and tank2_rec)

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    if tank1_anomaly:
        sp1 = max(0.05, sp1 - LOWER_STEP)
    elif sp1 < nom1:
        sp1 = min(nom1, sp1 + RESTORE_STEP)

    if tank2_anomaly:
        sp2 = max(0.05, sp2 - LOWER_STEP)
    elif sp2 < nom2:
        sp2 = min(nom2, sp2 + RESTORE_STEP)

    diag = ("tank1 anomaly=" + str(tank1_anomaly) +
            " (dT=" + str(round(dT, 2)) + "V, dS=" + str(round(dS, 2)) + "V); " +
            "tank2 anomaly=" + str(tank2_anomaly) +
            " (dT=" + str(round(dTr, 2)) + "V, dS=" + str(round(dSr, 2)) + "V)")

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
