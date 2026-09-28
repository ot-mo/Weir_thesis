def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---- fault-independent anchors measured on a healthy episode ----
    TOT_ANCHOR = 17.77      # mean(v1 + v2) [V]
    SPLIT_ANCHOR = 3.05     # mean(v1 - v2) [V]

    # 50-sample block gates.  A leak adds q to the total and 1/(1-2g)*q =
    # 1.667*q to the split, so the leak lives on a fixed slope in
    # (total, split) space and magnitude alone cannot separate it from the
    # healthy envelope (block-mean total up to ~20.3 V).
    DT1 = 2.2               # tank-1 direction (v2-rail caps q at 3.48 V)
    DT2 = 1.0               # tank-2 direction (v1-rail caps q at 1.19 V)
    SHAPE_LO = 1.35
    SHAPE_HI = 2.30
    ERR_CAP = 0.115         # healthy block-mean |error| = 0.074 / 0.083

    # Last-25-sample confirmation (a 25-sample mean has sqrt(2) x the
    # standard error of the 50-sample mean, hence the lower gates).
    DTR1 = 1.3
    DTR2 = 0.7
    SHAPE_LO_R = 1.05
    SHAPE_HI_R = 3.00
    ERR_CAP_R = 0.135

    LOWER_STEP = 0.005
    RESTORE_STEP = 0.01

    n = len(telemetry_window)
    if n < 4:
        return {
            "diagnosis": "telemetry too short for a block decision",
            "adjusted_setpoints": {
                "tank1": float(active_setpoints["tank1"]),
                "tank2": float(active_setpoints["tank2"]),
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
    err_ok_r = bool(e1_r < ERR_CAP_R and e2_r < ERR_CAP_R)

    # tank-1 direction: total up, split pushed down along the leak slope
    t1_full = bool(err_ok and dT > DT1
                   and dS <= -SHAPE_LO * dT and dS >= -SHAPE_HI * dT)
    # tank-2 direction: mirrored
    t2_full = bool(err_ok and dT > DT2
                   and dS >= SHAPE_LO * dT and dS <= SHAPE_HI * dT)
    t1_rec = bool(err_ok_r and dTr > DTR1
                  and dSr <= -SHAPE_LO_R * dTr and dSr >= -SHAPE_HI_R * dTr)
    t2_rec = bool(err_ok_r and dTr > DTR2
                  and dSr >= SHAPE_LO_R * dTr and dSr <= SHAPE_HI_R * dTr)

    tank1_anomaly = bool(t1_full and t1_rec)
    tank2_anomaly = bool(t2_full and t2_rec)

    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    floor1 = max(0.05, 0.92 * nom1)
    floor2 = max(0.05, 0.92 * nom2)

    if tank1_anomaly:
        sp1 = max(floor1, sp1 - LOWER_STEP)
    elif sp1 < nom1:
        sp1 = min(nom1, sp1 + RESTORE_STEP)

    if tank2_anomaly:
        sp2 = max(floor2, sp2 - LOWER_STEP)
    elif sp2 < nom2:
        sp2 = min(nom2, sp2 + RESTORE_STEP)

    diag = ("tank1 anomaly=" + str(tank1_anomaly) +
            " (dT=" + str(round(dT, 2)) + "V, dS=" + str(round(dS, 2)) +
            "V, |e|=" + str(round(e1_a, 3)) + "/" + str(round(e2_a, 3)) + "); " +
            "tank2 anomaly=" + str(tank2_anomaly) +
            " (dTr=" + str(round(dTr, 2)) + "V, dSr=" + str(round(dSr, 2)) + "V)")

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
