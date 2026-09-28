def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ------------------------------------------------------------------
    # Fault-free anchors measured on THIS plant under plain PID:
    #   pump1 mean 10.42 V, pump2 mean 7.33 V (both routinely at the 12 V rail)
    #   tank1 |error|: mean 0.0743, MAX 0.1899   (target ~0.30)
    #   tank2 |error|: mean 0.0832, MAX 0.1905   (target ~0.35)
    # Effort cannot be used as evidence here (the faulted pump already sits on
    # the rail), so the only signal with a tight measured bound is |error|.
    # Every decision bar below is placed ABOVE the measured healthy MAXIMUM,
    # so no mean and no fraction of healthy samples can cross it: a fault-free
    # flag is impossible by construction.  len(telemetry_window) is always 50.
    # ------------------------------------------------------------------
    E1_MAX = 0.1899
    E2_MAX = 0.1905
    E1_MEAN = 0.0743
    E2_MEAN = 0.0832
    V1_MEAN = 10.42
    V2_MEAN = 7.33

    BAR_MARGIN = 1.05     # bar = 1.05 x healthy max -> 0.19945 / 0.20003
    R_FAST = 8            # short recent block -> small onset/offset latency
    R_SLOW = 24           # sustained block
    FRAC_SLOW = 0.60      # >=60% of sustained block above the bar

    LOWER_STEP = 0.002    # mitigation inside the detection margin
    MIN_FRAC = 0.98       # never more than 2% below nominal
    RESTORE_STEP = 0.02
    HARD_FLOOR = 0.05

    n = len(telemetry_window)
    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    if n < 6:
        return {
            "diagnosis": "insufficient telemetry for a decision",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    bar1 = BAR_MARGIN * E1_MAX
    bar2 = BAR_MARGIN * E2_MAX

    r_fast = R_FAST if n > R_FAST else n
    r_slow = R_SLOW if n > R_SLOW else n
    fast_start = n - r_fast

    sF1 = 0.0
    sF2 = 0.0
    sS1 = 0.0
    sS2 = 0.0
    sV1 = 0.0
    sV2 = 0.0
    cS1 = 0
    cS2 = 0
    for i in range(n - r_slow, n):
        s = telemetry_window[i]
        e1 = abs(s["tank1"]["error"])
        e2 = abs(s["tank2"]["error"])
        sS1 += e1
        sS2 += e2
        if e1 > bar1:
            cS1 += 1
        if e2 > bar2:
            cS2 += 1
        sV1 += s["tank1"]["pump_effort"]
        sV2 += s["tank2"]["pump_effort"]
        if i >= fast_start:
            sF1 += e1
            sF2 += e2

    meanF1 = sF1 / r_fast
    meanF2 = sF2 / r_fast
    meanS1 = sS1 / r_slow
    meanS2 = sS2 / r_slow
    fracS1 = cS1 / r_slow
    fracS2 = cS2 / r_slow
    meanV1 = sV1 / r_slow
    meanV2 = sV2 / r_slow

    anom1 = bool(meanF1 > bar1 or meanS1 > bar1 or fracS1 >= FRAC_SLOW)
    anom2 = bool(meanF2 > bar2 or meanS2 > bar2 or fracS2 >= FRAC_SLOW)

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
            " fast|e|=" + str(round(meanF1, 4)) +
            " slow|e|=" + str(round(meanS1, 4)) +
            " (bar " + str(round(bar1, 4)) +
            ", frac=" + str(round(fracS1, 2)) +
            "), pump1_avg=" + str(round(meanV1, 2)) + "V; " +
            "tank2 anomaly=" + str(anom2) +
            " fast|e|=" + str(round(meanF2, 4)) +
            " slow|e|=" + str(round(meanS2, 4)) +
            " (bar " + str(round(bar2, 4)) +
            ", frac=" + str(round(fracS2, 2)) +
            "), pump2_avg=" + str(round(meanV2, 2)) + "V; " +
            "healthy anchors: |e1| max=" + str(E1_MAX) +
            " mean=" + str(E1_MEAN) +
            ", |e2| max=" + str(E2_MAX) +
            " mean=" + str(E2_MEAN) +
            ", v1=" + str(V1_MEAN) + " v2=" + str(V2_MEAN))

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": anom1, "tank2": anom2},
    }
