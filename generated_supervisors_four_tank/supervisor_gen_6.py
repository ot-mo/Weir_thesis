def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ------------------------------------------------------------------
    # Fault-free anchors MEASURED on this plant under plain PID (no supervisor),
    # all statistics over a 50-second window:
    #   |e1| (tank1) mean 0.0743, max 0.1899   (target ~0.30)
    #   |e2| (tank2) mean 0.0832, max 0.1905   (target ~0.35)
    #   v1 mean 10.42 V, v2 mean 7.33 V, both with range maxima at the 12 V rail
    # Pump effort is deliberately NOT part of the decision: healthy pumps hug the
    # supply rail (v1 max 12.00 V, v2 max 12.00 V) and oscillate anti-phase in
    # this non-minimum-phase configuration, so sustained high effort is a healthy
    # artifact.  The only quantity with a hard measured ceiling is |error|.
    #
    # Both decision bars sit STRICTLY ABOVE the measured healthy MAXIMUM, so no
    # healthy sample can cross them and no mean/count over any block of healthy
    # samples can either: a fault-free flag is impossible by construction.
    # Sensitivity is bought only in the decision-window LENGTH: a short 8-sample
    # block keeps the onset latency (missed anomalies) and the post-clear release
    # latency (false positives) small, so no large symmetric missed/false pair
    # can accumulate.  len(telemetry_window) is ALWAYS exactly 50.
    # ------------------------------------------------------------------
    E1_MAX = 0.1899
    E2_MAX = 0.1905
    E1_MEAN = 0.0743
    E2_MEAN = 0.0832
    V1_MEAN = 10.42
    V2_MEAN = 7.33

    BAR_MARGIN = 1.05   # bar1 = 0.19945, bar2 = 0.20003 (above healthy maxima)
    W = 8               # short recent decision block (always <= 50)
    K = 3               # at least 3 of the last 8 samples above the bar

    MIT_STEP = 0.002    # mitigation step, capped well inside the detection margin
    MIN_FRAC = 0.98     # never more than 2% below nominal
    RESTORE_STEP = 0.02
    HARD_FLOOR = 0.05

    n = len(telemetry_window)
    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    if n < 3:
        return {
            "diagnosis": "insufficient telemetry for a decision",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    bar1 = BAR_MARGIN * E1_MAX
    bar2 = BAR_MARGIN * E2_MAX

    w = W if n > W else n
    start = n - w

    c1 = 0
    c2 = 0
    s1 = 0.0
    s2 = 0.0
    sV1 = 0.0
    sV2 = 0.0
    for i in range(start, n):
        smp = telemetry_window[i]
        e1 = abs(smp["tank1"]["error"])
        e2 = abs(smp["tank2"]["error"])
        s1 = s1 + e1
        s2 = s2 + e2
        sV1 = sV1 + smp["tank1"]["pump_effort"]
        sV2 = sV2 + smp["tank2"]["pump_effort"]
        if e1 > bar1:
            c1 = c1 + 1
        if e2 > bar2:
            c2 = c2 + 1

    mean1 = s1 / w
    mean2 = s2 / w
    meanV1 = sV1 / w
    meanV2 = sV2 / w

    # Both routes are unreachable for healthy data (healthy |e| <= max < bar).
    anom1 = bool(c1 >= K or mean1 > bar1)
    anom2 = bool(c2 >= K or mean2 > bar2)

    floor1 = max(HARD_FLOOR, MIN_FRAC * nom1)
    floor2 = max(HARD_FLOOR, MIN_FRAC * nom2)

    if anom1:
        sp1 = max(floor1, sp1 - MIT_STEP)
    elif sp1 < nom1:
        sp1 = min(nom1, sp1 + RESTORE_STEP)

    if anom2:
        sp2 = max(floor2, sp2 - MIT_STEP)
    elif sp2 < nom2:
        sp2 = min(nom2, sp2 + RESTORE_STEP)

    diag = ("tank1 anomaly=" + str(anom1) +
            " over_bar=" + str(c1) + "/" + str(w) +
            " mean|e|=" + str(round(mean1, 4)) +
            " (bar=" + str(round(bar1, 4)) +
            ", healthy max=" + str(E1_MAX) +
            " mean=" + str(E1_MEAN) +
            ", pump1_avg=" + str(round(meanV1, 2)) + "V); " +
            "tank2 anomaly=" + str(anom2) +
            " over_bar=" + str(c2) + "/" + str(w) +
            " mean|e|=" + str(round(mean2, 4)) +
            " (bar=" + str(round(bar2, 4)) +
            ", healthy max=" + str(E2_MAX) +
            " mean=" + str(E2_MEAN) +
            ", pump2_avg=" + str(round(meanV2, 2)) + "V); " +
            "healthy effort anchors v1=" + str(V1_MEAN) +
            " v2=" + str(V2_MEAN) + " (effort not used as evidence)")

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": anom1, "tank2": anom2},
    }
