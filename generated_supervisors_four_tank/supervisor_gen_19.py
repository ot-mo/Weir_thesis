def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---- fault-independent anchors measured on a healthy, fault-free episode ----
    TOT_ANCHOR = 17.77      # mean(v1 + v2) [V]
    SPLIT_ANCHOR = 3.05     # mean(v1 - v2) [V]

    # Tier A: large total excess; shape band loose, but still fill-immune by
    # geometry (symmetric fill gives |dS| = 3.05 V, i.e. ratio 3.05/dT <= 1.17
    # for dT >= 2.6).
    DT_STRONG = 2.6
    SL_STRONG = 1.45
    SH_STRONG = 2.05

    # Tier B: smaller total excess, paid for with the exact leak ratio
    # |dS|/dT = 1/(1 - 2*gamma) = 1.667 (+/- 10%), an absolute split floor and
    # a sustained-shift (sub-block) persistence test.
    DT_WEAK = 1.8
    SL_WEAK = 1.52
    SH_WEAK = 1.86
    DS_FLOOR1 = 2.6

    # Mirrored tank-2 tier: the 12 V rail caps a compensated tank-2 signature,
    # so the gate is set above that cap - structurally present, but it can
    # never be an FP source on healthy data.
    DT_WEAK2 = 2.1
    SL_WEAK2 = 1.52
    SH_WEAK2 = 1.86
    DS_FLOOR2 = 3.0

    # Trailing 25-sample confirmation (same shape, relaxed magnitude).
    DT_REC = 1.5
    SL_REC = 1.40
    SH_REC = 2.10

    # Healthy block-mean |error| is 0.0740 (h1) / 0.0832 (h2); start-up fill
    # sits near 0.25, the rail-pinned anti-phase plateau above 0.083.
    ERR_CAP = 0.12

    # Sustained-shift persistence across the 5 ten-sample sub-blocks of the
    # 50-sample window.
    SUB_DT = 0.45
    SUB_RATIO = 1.10
    SUB_MIN = 3

    LOWER_STEP = 0.02
    RESTORE_STEP = 0.03

    n = len(telemetry_window)
    if n < 12:
        return {
            "diagnosis": "telemetry too short for a block decision",
            "adjusted_setpoints": {
                "tank1": active_setpoints["tank1"],
                "tank2": active_setpoints["tank2"],
            },
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    def block(lo, hi):
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

    tot, spl, e1, e2 = block(0, n)
    half = n // 2
    if half < 1:
        half = 1
    tot_r, spl_r, e1_r, e2_r = block(n - half, n)

    dT = tot - TOT_ANCHOR
    dS = spl - SPLIT_ANCHOR
    dTr = tot_r - TOT_ANCHOR
    dSr = spl_r - SPLIT_ANCHOR

    err_ok = bool(e1 < ERR_CAP and e2 < ERR_CAP)
    err_ok_r = bool(e1_r < ERR_CAP and e2_r < ERR_CAP)

    # sustained-shift persistence: how many of the 5 sub-blocks already show
    # the same signed, shape-consistent displacement (the healthy loop is
    # oscillatory, so a genuine sustained shift is what survives this).
    m = n // 5
    ok1 = 0
    ok2 = 0
    if m >= 4:
        for k in range(5):
            bt, bs, _, _ = block(k * m, (k + 1) * m)
            dk = bt - TOT_ANCHOR
            sk = bs - SPLIT_ANCHOR
            if dk > SUB_DT and sk <= -SUB_RATIO * dk:
                ok1 += 1
            if dk > SUB_DT and sk >= SUB_RATIO * dk:
                ok2 += 1
    persist1 = bool(ok1 >= SUB_MIN)
    persist2 = bool(ok2 >= SUB_MIN)

    # ---------------- tank 1: total up, split pushed DOWN, |dS|/dT ~ 1.667 ----
    rec1 = bool(dTr > DT_REC and dSr <= -SL_REC * dTr
                and dSr >= -SH_REC * dTr and err_ok_r)
    strong1 = bool(dT > DT_STRONG and dS <= -SL_STRONG * dT
                   and dS >= -SH_STRONG * dT and err_ok)
    weak1 = bool(dT > DT_WEAK and dS <= -SL_WEAK * dT
                 and dS >= -SH_WEAK * dT and dS <= -DS_FLOOR1
                 and err_ok and persist1)
    tank1_anomaly = bool(rec1 and (strong1 or weak1))

    # ---------------- tank 2: mirrored -------------------------------------
    rec2 = bool(dTr > DT_REC and dSr >= SL_REC * dTr
                and dSr <= SH_REC * dTr and err_ok_r)
    strong2 = bool(dT > DT_STRONG and dS >= SL_STRONG * dT
                   and dS <= SH_STRONG * dT and err_ok)
    weak2 = bool(dT > DT_WEAK2 and dS >= SL_WEAK2 * dT
                 and dS <= SH_WEAK2 * dT and dS >= DS_FLOOR2
                 and err_ok and persist2)
    tank2_anomaly = bool(rec2 and (strong2 or weak2))

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
            " (dTr=" + str(round(dTr, 2)) + "V, dSr=" + str(round(dSr, 2)) + "V)")

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
