def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---- fault-independent anchors (measured healthy, fault-free episode) --
    TOT_ANCHOR = 17.77      # healthy 50 s mean of v1+v2  [V]
    SPLIT_ANCHOR = 3.05     # healthy 50 s mean of v1-v2  [V]

    # Block-mean total-excess gates. Healthy 50 s block-mean total has been
    # measured up to ~20.3 V, i.e. dT <= ~2.5 V. The pump rails cap the leak
    # signature at q <= 3.48 V (tank 1: the extra flow must go through v2,
    # 7.36+1.333*q <= 12) and q <= 1.19 V (tank 2: through v1,
    # 10.41+1.333*q <= 12), so the gate pair is forced to be asymmetric and
    # must sit below the smallest excess to be detected, not below the noise.
    DT_GATE_T1 = 2.0
    DT_GATE_T2 = 1.0

    # Leak shape constant dS/dT = 1/(1-2*gamma) ~= 1.667; invariant in fault
    # magnitude and in the faulted fraction of the block (both deviations
    # scale with the same mixture factor), so it is safe on partial blocks.
    SHAPE_LO = 1.35
    SHAPE_HI = 2.15

    # Nested 25 s confirmation at HALF the primary gate: the recent mean
    # reacts faster than the 50 s mean on the way down after a clear, so the
    # AND truncates the post-clear flag tail without adding onset latency.
    # The band is widened because a B/2-sample ratio carries sqrt(2) more
    # relative noise than the B-sample ratio.
    DT_GATE_T1_R = 1.0
    DT_GATE_T2_R = 0.5
    SHAPE_LO_R = 1.10
    SHAPE_HI_R = 2.45

    # Error guards. Measured healthy 50 s block-mean |error| <= 0.085 m for
    # both tanks (per-sample means 0.074 / 0.083); the start-up fill and any
    # rail-pinned off-target plateau exceed 0.13-0.18 m, so this channel
    # carries the false-positive defence that gate height cannot carry here.
    ERR_TOL1 = 0.105
    ERR_TOL2 = 0.110

    # Setpoint trim: small and bounded, always the first thing walked back.
    TRIM = 0.01
    RESTORE = 0.05
    MAX_TRIM = 0.10

    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    n = len(telemetry_window)
    if n < 8:
        return {
            "diagnosis": "insufficient telemetry (n<8): no decision",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    # ---- full-window block means (n is 50 in this plant) ------------------
    tot = 0.0
    spl = 0.0
    e1 = 0.0
    e2 = 0.0
    for s in telemetry_window:
        a = s["tank1"]["pump_effort"]
        b = s["tank2"]["pump_effort"]
        tot += a + b
        spl += a - b
        e1 += abs(s["tank1"]["error"])
        e2 += abs(s["tank2"]["error"])
    tot = tot / n
    spl = spl / n
    e1 = e1 / n
    e2 = e2 / n

    # ---- most recent half, nested confirmation ---------------------------
    m = n - (n // 2)
    rtot = 0.0
    rspl = 0.0
    re1 = 0.0
    re2 = 0.0
    for i in range(n - m, n):
        s = telemetry_window[i]
        a = s["tank1"]["pump_effort"]
        b = s["tank2"]["pump_effort"]
        rtot += a + b
        rspl += a - b
        re1 += abs(s["tank1"]["error"])
        re2 += abs(s["tank2"]["error"])
    rtot = rtot / m
    rspl = rspl / m
    re1 = re1 / m
    re2 = re2 / m

    dT = tot - TOT_ANCHOR
    dS = spl - SPLIT_ANCHOR
    dTr = rtot - TOT_ANCHOR
    dSr = rspl - SPLIT_ANCHOR

    err_ok = bool(e1 <= ERR_TOL1 and e2 <= ERR_TOL2)
    err_ok_r = bool(re1 <= ERR_TOL1 + 0.02 and re2 <= ERR_TOL2 + 0.02)

    # tank-1 leak: extra flow routed through v2 -> split pushed DOWN
    t1_full = bool(dT >= DT_GATE_T1 and
                   dS <= -SHAPE_LO * dT and dS >= -SHAPE_HI * dT)
    # tank-2 leak: extra flow routed through v1 -> split pushed UP
    t2_full = bool(dT >= DT_GATE_T2 and
                   dS >= SHAPE_LO * dT and dS <= SHAPE_HI * dT)
    t1_rec = bool(dTr >= DT_GATE_T1_R and
                  dSr <= -SHAPE_LO_R * dTr and dSr >= -SHAPE_HI_R * dTr)
    t2_rec = bool(dTr >= DT_GATE_T2_R and
                  dSr >= SHAPE_LO_R * dTr and dSr <= SHAPE_HI_R * dTr)

    tank1_anomaly = bool(err_ok and err_ok_r and t1_full and t1_rec)
    tank2_anomaly = bool(err_ok and err_ok_r and t2_full and t2_rec)

    if tank1_anomaly:
        sp1 = max(nom1 - MAX_TRIM, sp1 - TRIM)
    elif sp1 < nom1:
        sp1 = min(nom1, sp1 + RESTORE)

    if tank2_anomaly:
        sp2 = max(nom2 - MAX_TRIM, sp2 - TRIM)
    elif sp2 < nom2:
        sp2 = min(nom2, sp2 + RESTORE)

    diag = ("tank1 anomaly=" + str(tank1_anomaly) +
            " (dT=" + str(round(dT, 2)) + "V, dS=" + str(round(dS, 2)) +
            "V, |e1|=" + str(round(e1, 3)) + "); tank2 anomaly=" +
            str(tank2_anomaly) + " (dT25=" + str(round(dTr, 2)) +
            "V, dS25=" + str(round(dSr, 2)) + "V, |e2|=" + str(round(e2, 3)) +
            ")")

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
