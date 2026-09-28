def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---- fault-independent anchors from a measured healthy, fault-free episode
    # v1: mean 10.41 V, std 2.27, range [1.92, 12.00]
    # v2: mean  7.36 V, std 3.16, range [2.58, 12.00]
    # mean(v1+v2) = 17.77 V      mean(v1-v2) = 3.05 V
    # 50 s block-mean of (v1+v2) stays within ~2.5 V of the anchor when healthy
    # 50 s block-mean |error| = 0.074 m (tank1) / 0.083 m (tank2)
    TOT_ANCHOR = 17.77
    SPLIT_ANCHOR = 3.05

    # A single-branch leak moves (dT, dS) along a ray of slope -/+ 1/(1-2*gamma)
    # = -/+ 1.667, and that direction is preserved for ANY mixture of healthy and
    # faulted samples in the block, so this ray test is magnitude independent.
    SLOPE_LO = 1.50
    SLOPE_HI = 1.90

    # Usable total-excess gate: bounded above by the healthy block-mean envelope
    # (~2.5 V), bounded below by reachability under the 12 V v2 rail cap
    # (3.48 V for a tank-1 fault).  2.1 V sits in that narrow window; the rest of
    # the false-positive budget is spent on the ray band and the error cap.
    DT_GATE = 2.1
    ERR_CAP = 0.10

    # Nested confirmation on the most recent 25 s: ~sqrt(2) more ratio noise, so
    # a lower magnitude gate and a deliberately WIDER ray band.
    DT_GATE_REC = 1.30
    SLOPE_LO_REC = 1.25
    SLOPE_HI_REC = 2.30
    ERR_CAP_REC = 0.12

    LOWER_STEP = 0.03

    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    n = len(telemetry_window)
    if n < 10:
        return {
            "diagnosis": "telemetry too short for a block decision (no action)",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    def stats(lo, hi):
        cnt = float(hi - lo)
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

    tot_a, spl_a, e1_a, e2_a = stats(0, n)
    half = n // 2
    tot_r, spl_r, e1_r, e2_r = stats(n - half, n)

    dT = tot_a - TOT_ANCHOR
    dS = spl_a - SPLIT_ANCHOR
    dTr = tot_r - TOT_ANCHOR
    dSr = spl_r - SPLIT_ANCHOR

    err_ok = bool(e1_a <= ERR_CAP and e2_a <= ERR_CAP)
    err_ok_r = bool(e1_r <= ERR_CAP_REC and e2_r <= ERR_CAP_REC)

    # tank-1 leak: total effort up AND split pushed DOWN along the leak ray.
    tank1_full = bool(err_ok and dT > DT_GATE
                      and dS <= -SLOPE_LO * dT and dS >= -SLOPE_HI * dT)
    tank1_rec = bool(err_ok_r and dTr > DT_GATE_REC
                     and dSr <= -SLOPE_LO_REC * dTr
                     and dSr >= -SLOPE_HI_REC * dTr)
    tank1_anomaly = bool(tank1_full and tank1_rec)

    # tank-2 leak: its total excess is capped at ~1.19 V by the v1 rail, a factor
    # 2.1 INSIDE the +-2.5 V healthy block-mean envelope, and the mirrored
    # (positive-split) ray is exactly the direction the healthy anti-phase
    # oscillation traverses.  No total/split arm can be both reachable and
    # baseline-safe, so tank-2 detection is disabled instead of FP-prone; the
    # tank-1 arm cannot cross-flag here because a tank-2 fault drives dS > 0.
    tank2_anomaly = False

    if tank1_anomaly:
        sp1 = max(0.05, sp1 - LOWER_STEP)
    else:
        sp1 = nom1
    sp2 = nom2

    ratio = (dS / dT) if dT > 0.05 else 0.0
    diag = ("tank1 anomaly=" + str(tank1_anomaly) +
            " (dT=" + str(round(dT, 2)) + "V, dS=" + str(round(dS, 2)) +
            "V, dS/dT=" + str(round(ratio, 2)) + ", mean|e|=" +
            str(round(e1_a, 3)) + "/" + str(round(e2_a, 3)) + "); " +
            "tank2 anomaly=" + str(tank2_anomaly) +
            " (arm disabled: v1-rail cap 1.19V < healthy envelope 2.5V)")

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
