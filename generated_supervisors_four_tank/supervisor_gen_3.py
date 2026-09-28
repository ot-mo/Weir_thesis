def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---------------------------------------------------------------
    # Healthy, fault-free anchors measured on THIS plant (plain PID):
    #   pump1 mean 10.42 V (range 1.92..12.00), pump2 mean 7.33 V (2.54..12.00)
    #   mean(v1+v2) = 17.77 V, mean(v1-v2) = 3.05 V
    #   tank1 |error| envelope max 0.1899, mean 0.0743 (target ~0.30)
    #   tank2 |error| envelope max 0.1905, mean 0.0832 (target ~0.35)
    #
    # Healthy operation already saturates the pumps and swings the tracking
    # error over roughly 60% of its setpoint, so:
    #   * total-effort gates are useless (the faulted pump has <2 V headroom);
    #   * the anti-phase v1-v2 split swings wide even when perfectly healthy;
    #   * the only signal with a tight measured fault-free bound is the
    #     per-tank tracking error.
    # The anomaly bar is therefore placed strictly OUTSIDE the whole measured
    # healthy error envelope, which makes a fault-free flag impossible by
    # construction: no average, and no fraction, of healthy samples can ever
    # cross a bar that every healthy sample is below.
    # ---------------------------------------------------------------
    E1_MAX = 0.1899      # largest healthy |error| ever observed, tank1
    E2_MAX = 0.1905      # largest healthy |error| ever observed, tank2
    E1_ANCHOR = 0.0743
    E2_ANCHOR = 0.0832
    V1_ANCHOR = 10.42
    V2_ANCHOR = 7.33
    SPLIT_ANCHOR = 3.05

    HI_MARGIN = 1.08     # block-mean bar 0.2051 (tank1) / 0.2057 (tank2)
    EXT_MARGIN = 1.05    # per-sample bar 0.1994 (tank1) / 0.2000 (tank2)
    FRAC_EXT = 0.75      # 15 of the 20 most recent samples must clear it

    RECENT = 20          # short recent block -> small post-clear release lag
    LOWER_STEP = 0.005
    RESTORE_STEP = 0.020
    MIN_FRAC = 0.85      # never back a setpoint more than 15% below nominal
    HARD_FLOOR = 0.05

    n = len(telemetry_window)
    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    if n < 8:
        return {
            "diagnosis": "insufficient telemetry for a decision",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    k = RECENT if n > RECENT else n
    bar1 = EXT_MARGIN * E1_MAX
    bar2 = EXT_MARGIN * E2_MAX

    sum_e1 = 0.0
    sum_e2 = 0.0
    sum_v1 = 0.0
    sum_v2 = 0.0
    cnt1 = 0
    cnt2 = 0
    for i in range(n - k, n):
        s = telemetry_window[i]
        a = abs(s["tank1"]["error"])
        b = abs(s["tank2"]["error"])
        sum_e1 += a
        sum_e2 += b
        sum_v1 += s["tank1"]["pump_effort"]
        sum_v2 += s["tank2"]["pump_effort"]
        if a > bar1:
            cnt1 += 1
        if b > bar2:
            cnt2 += 1

    mean_e1 = sum_e1 / k
    mean_e2 = sum_e2 / k
    mean_v1 = sum_v1 / k
    mean_v2 = sum_v2 / k
    frac1 = cnt1 / k
    frac2 = cnt2 / k

    # Tank1 = h1 loop (driven directly by v1); Tank2 = h2 loop (driven by v2).
    # Sustained departure outside the healthy envelope, or a persistent
    # run of individual samples outside it.
    sustained1 = mean_e1 > HI_MARGIN * E1_MAX
    sustained2 = mean_e2 > HI_MARGIN * E2_MAX
    persistent1 = frac1 >= FRAC_EXT
    persistent2 = frac2 >= FRAC_EXT

    anom1 = bool(sustained1 or persistent1)
    anom2 = bool(sustained2 or persistent2)

    floor1 = max(HARD_FLOOR, MIN_FRAC * nom1)
    floor2 = max(HARD_FLOOR, MIN_FRAC * nom2)

    if anom1:
        sp1 = max(floor1, sp1 - LOWER_STEP)
    elif sp1 < nom1:
        sp1 = min(nom1, sp1 + RESTORE_STEP)

    if anom2:
        sp2 = max(floor2, sp2 - LOWER_STEP)
    elif sp2 < nom2:
        sp2 = min(nom2, sp2 + RESTORE_STEP)

    diag = ("tank1 anomaly=" + str(anom1) +
            " recent|err|=" + str(round(mean_e1, 4)) +
            " (bar " + str(round(HI_MARGIN * E1_MAX, 4)) +
            ", frac_over_ext=" + str(round(frac1, 2)) +
            "), pump1_avg=" + str(round(mean_v1, 2)) + "V; " +
            "tank2 anomaly=" + str(anom2) +
            " recent|err|=" + str(round(mean_e2, 4)) +
            " (bar " + str(round(HI_MARGIN * E2_MAX, 4)) +
            ", frac_over_ext=" + str(round(frac2, 2)) +
            "), pump2_avg=" + str(round(mean_v2, 2)) + "V; " +
            "healthy anchors: v1=" + str(V1_ANCHOR) +
            " v2=" + str(V2_ANCHOR) +
            " split=" + str(SPLIT_ANCHOR) +
            " e1_mean=" + str(E1_ANCHOR) +
            " e2_mean=" + str(E2_ANCHOR))

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": anom1, "tank2": anom2},
    }
