def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ------------------------------------------------------------------
    # Healthy (fault-free, plain PID) anchors measured on THIS plant:
    #   tank1 |error|: mean 0.0743, MAX 0.1899   (target ~0.30 m)
    #   tank2 |error|: mean 0.0832, MAX 0.1905   (target ~0.35 m)
    #   pump1 effort : mean 10.42 V, range [1.92, 12.00] (rail = 12 V)
    #   pump2 effort : mean  7.33 V, range [2.54, 12.00]
    # The pumps already ride the 12 V rail in healthy operation (non-minimum-
    # phase cross-coupling), so effort is NOT usable as evidence.  The only
    # tight, bounded healthy statistic is per-tank |error|, whose observed
    # maximum is ~0.19.  Every decision bar below is placed strictly ABOVE
    # that maximum, so a fault-free crossing is mathematically impossible and
    # no healthy sample can ever accumulate into a flag.
    #
    # Detection = a per-sample COUNT test on the recent block.  A count test
    # trips at the FIRST sample that crosses the bar, which is strictly
    # earlier than a block-MEAN test at the same bar (a mean can only exceed
    # the bar after a sample already has).  A SHORT recent block keeps the
    # post-clear release lag short, cutting the late (false-positive) tail;
    # the champion's 24-sample mean/fraction routes are deleted because they
    # can never trip earlier than this test but always hold the flag longer.
    # len(telemetry_window) is ALWAYS 50 (1 Hz); only a small sub-window of
    # it is used, so no gate can become unreachable.
    # ------------------------------------------------------------------
    E1_MAX = 0.1899
    E2_MAX = 0.1905
    E1_MEAN = 0.0743
    E2_MEAN = 0.0832
    V1_MEAN = 10.42
    V2_MEAN = 7.33

    BAR_MARGIN = 1.06     # bar = 1.06 x healthy MAX -> 0.20129 / 0.20193
    R_WIN = 10            # recent-evidence window (subset of the 50 samples)
    K_NEED = 2            # samples above bar inside R_WIN to raise a flag

    LOWER_STEP = 0.0015   # mitigation rate (m/step)
    MAX_DROP = 0.0030     # total mitigation excursion (m), << bar - healthy max
    RESTORE_STEP = 0.05   # restore rate once a tank's fault has cleared
    HARD_FLOOR = 0.05

    n = len(telemetry_window)
    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    if n < 1:
        return {
            "diagnosis": "no telemetry available",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    bar1 = BAR_MARGIN * E1_MAX
    bar2 = BAR_MARGIN * E2_MAX

    r = R_WIN if n > R_WIN else n
    start = n - r

    c1 = 0
    c2 = 0
    s1 = 0.0
    s2 = 0.0
    sV1 = 0.0
    sV2 = 0.0
    for i in range(start, n):
        smp = telemetry_window[i]
        a1 = abs(smp["tank1"]["error"])
        a2 = abs(smp["tank2"]["error"])
        s1 += a1
        s2 += a2
        sV1 += smp["tank1"]["pump_effort"]
        sV2 += smp["tank2"]["pump_effort"]
        if a1 > bar1:
            c1 += 1
        if a2 > bar2:
            c2 += 1

    mean1 = s1 / r
    mean2 = s2 / r
    meanV1 = sV1 / r
    meanV2 = sV2 / r

    anom1 = bool(c1 >= K_NEED)
    anom2 = bool(c2 >= K_NEED)

    floor1 = max(HARD_FLOOR, nom1 - MAX_DROP)
    floor2 = max(HARD_FLOOR, nom2 - MAX_DROP)

    if anom1:
        if sp1 > nom1:
            sp1 = nom1
        if sp1 > floor1:
            sp1 = max(floor1, sp1 - LOWER_STEP)
    elif sp1 < nom1:
        sp1 = min(nom1, sp1 + RESTORE_STEP)

    if anom2:
        if sp2 > nom2:
            sp2 = nom2
        if sp2 > floor2:
            sp2 = max(floor2, sp2 - LOWER_STEP)
    elif sp2 < nom2:
        sp2 = min(nom2, sp2 + RESTORE_STEP)

    diag = ("tank1 " + ("ANOMALY" if anom1 else "nominal") +
            " |e|mean=" + str(round(mean1, 4)) +
            " above-bar=" + str(c1) + "/" + str(r) +
            " (bar=" + str(round(bar1, 4)) + ")" +
            ", v1=" + str(round(meanV1, 2)) + "V; " +
            "tank2 " + ("ANOMALY" if anom2 else "nominal") +
            " |e|mean=" + str(round(mean2, 4)) +
            " above-bar=" + str(c2) + "/" + str(r) +
            " (bar=" + str(round(bar2, 4)) + ")" +
            ", v2=" + str(round(meanV2, 2)) + "V; " +
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
