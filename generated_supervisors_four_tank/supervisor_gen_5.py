def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ------------------------------------------------------------------
    # Fault-free envelope measured on THIS plant under plain PID:
    #   tank1 |error|: mean 0.0743, max 0.1899   (target ~0.30)
    #   tank2 |error|: mean 0.0832, max 0.1905   (target ~0.35)
    #   pump1 effort:  mean 10.42 V, range [1.92, 12.00] V
    #   pump2 effort:  mean  7.33 V, range [2.54, 12.00] V
    # Pump effort cannot be primary evidence: both pumps routinely sit on the
    # 12 V rail in healthy operation (anti-phase, non-minimum-phase loop).
    # The only tightly bounded signal is |error|, so the bar sits just above
    # the measured healthy MAXIMUM.  Because the statistic tested is a mean
    # (or a sample fraction) of the most recent 16 samples, it can never
    # exceed that maximum, so a fault-free flag is impossible by construction
    # and no amount of healthy oscillation can cross it.  Sensitivity is
    # bought from the SHORT recent window (16 s), not from the bar.
    # len(telemetry_window) is ALWAYS exactly 50; never gate on larger n.
    # ------------------------------------------------------------------
    E1_MAX = 0.1899
    E2_MAX = 0.1905

    BAR_MULT = 1.02       # bar = 1.02 x healthy max -> 0.1937 / 0.1943
    R_RECENT = 16         # short decision window -> low onset & release lag
    FRAC_RECENT = 0.5     # >=50% of the 16 recent samples above the bar
    SAT_LEVEL = 11.9      # 99.2% of the 12 V supply
    SAT_ERR = 0.19        # corroboration: |error| still at healthy max

    MIT_FRAC_STEP = 0.001  # 0.1% of nominal per step, bounded well inside
    FLOOR_FRAC = 0.995     # detection margin (~0.015 m at these setpoints)
    RESTORE_STEP = 0.02    # 2% of nominal per step -> gap closes fast
    HARD_FLOOR = 0.05

    n = len(telemetry_window)
    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    if n < 1:
        return {
            "diagnosis": "insufficient telemetry for a decision",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    bar1 = BAR_MULT * E1_MAX
    bar2 = BAR_MULT * E2_MAX
    r = R_RECENT if n > R_RECENT else n

    s1 = 0.0
    s2 = 0.0
    v1 = 0.0
    v2 = 0.0
    c1 = 0
    c2 = 0
    for i in range(n - r, n):
        s = telemetry_window[i]
        e1 = abs(s["tank1"]["error"])
        e2 = abs(s["tank2"]["error"])
        s1 += e1
        s2 += e2
        v1 += s["tank1"]["pump_effort"]
        v2 += s["tank2"]["pump_effort"]
        if e1 > bar1:
            c1 += 1
        if e2 > bar2:
            c2 += 1

    m1 = s1 / r
    m2 = s2 / r
    mv1 = v1 / r
    mv2 = v2 / r
    f1 = c1 / r
    f2 = c2 / r

    # Route 1: recent block-mean |error| above a bar placed above the healthy
    # maximum, or a majority of the recent samples above that bar.
    a1 = bool(m1 > bar1 or f1 >= FRAC_RECENT)
    a2 = bool(m2 > bar2 or f2 >= FRAC_RECENT)
    # Route 2: pump living on the supply rail for a full 16 s while tracking
    # error is still as large as the healthy envelope maximum (healthy
    # saturation spikes are single samples, not a 16 s average).
    if mv1 > SAT_LEVEL and m1 > SAT_ERR:
        a1 = True
    if mv2 > SAT_LEVEL and m2 > SAT_ERR:
        a2 = True

    floor1 = max(HARD_FLOOR, FLOOR_FRAC * nom1)
    floor2 = max(HARD_FLOOR, FLOOR_FRAC * nom2)

    if a1:
        sp1 = max(floor1, sp1 - MIT_FRAC_STEP * nom1)
    elif sp1 < nom1:
        sp1 = min(nom1, sp1 + RESTORE_STEP * nom1)

    if a2:
        sp2 = max(floor2, sp2 - MIT_FRAC_STEP * nom2)
    elif sp2 < nom2:
        sp2 = min(nom2, sp2 + RESTORE_STEP * nom2)

    diag = ("tank1 anomaly=" + str(a1) +
            " recent%d|e|=" % r + str(round(m1, 4)) +
            " (bar " + str(round(bar1, 4)) +
            ", frac=" + str(round(f1, 2)) +
            ", pump1_avg16=" + str(round(mv1, 2)) + "V); " +
            "tank2 anomaly=" + str(a2) +
            " recent%d|e|=" % r + str(round(m2, 4)) +
            " (bar " + str(round(bar2, 4)) +
            ", frac=" + str(round(f2, 2)) +
            ", pump2_avg16=" + str(round(mv2, 2)) + "V); " +
            "healthy envelope: |e1| max=" + str(E1_MAX) +
            " |e2| max=" + str(E2_MAX) +
            " -> bars placed above these maxima")

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": a1, "tank2": a2},
    }
