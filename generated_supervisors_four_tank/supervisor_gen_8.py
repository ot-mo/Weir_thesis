def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ------------------------------------------------------------------
    # Measured healthy, fault-free envelope on THIS plant (plain PID, no
    # supervisor action at all - hard numbers):
    #   tank1 |error| mean 0.0743, MAX 0.1899 (target ~0.30)
    #   tank2 |error| mean 0.0832, MAX 0.1905 (target ~0.35)
    #   v1 mean 10.42 V, v2 mean 7.33 V, both routinely touching the 12 V rail
    #   levels 0.05-0.48 m, settling 100-300 s
    # len(telemetry_window) is ALWAYS exactly 50 (1 Hz, 50 s of history).
    #
    # Decision signal: per-tank |error|, the only quantity with a hard measured
    # healthy ceiling.  The bar is 1.05 x that ceiling, so NO healthy sample
    # can ever reach it and the count route can never fire on fault-free data,
    # no matter what phase the anti-phase control-loop oscillation is in.
    # Persistence is a plain count (K=2 of the last W=10 samples) rather than a
    # block mean or a fraction-of-block: at the same bar a mean/fraction route
    # can only engage LATER than the count (a block average cannot exceed the
    # bar before one of its samples does) and it holds the flag True for as
    # long as its longer averaging window still contains pre-clear samples,
    # i.e. it is pure release lag.  K=2 costs one sample of onset latency but
    # removes single-outlier false positives, which matters because the
    # healthy ceiling is estimated from one finite healthy episode.
    # Effort is deliberately NOT used: v1 already touches its 12 V rail when
    # nothing is wrong, so any absolute-voltage rule false-positives.
    # ------------------------------------------------------------------
    E1_MAX = 0.1899
    E2_MAX = 0.1905
    E1_MEAN = 0.0743
    E2_MEAN = 0.0832
    V1_MEAN = 10.42
    V2_MEAN = 7.33

    BAR_MARGIN = 1.05     # bar is 5% above the measured healthy maximum
    W = 10                # recent decision block (window is always 50)
    K = 2                 # 2 hot samples inside the last W -> flag

    LOWER_STEP = 0.001    # negligible, strictly bounded mitigation
    MIN_FRAC = 0.995      # never more than 0.5% below nominal
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
    se1 = 0.0
    se2 = 0.0
    sv1 = 0.0
    sv2 = 0.0
    for i in range(start, n):
        s = telemetry_window[i]
        e1 = abs(float(s["tank1"]["error"]))
        e2 = abs(float(s["tank2"]["error"]))
        se1 = se1 + e1
        se2 = se2 + e2
        sv1 = sv1 + float(s["tank1"]["pump_effort"])
        sv2 = sv2 + float(s["tank2"]["pump_effort"])
        if e1 > bar1:
            c1 = c1 + 1
        if e2 > bar2:
            c2 = c2 + 1

    anom1 = bool(c1 >= K)
    anom2 = bool(c2 >= K)

    floor1 = HARD_FLOOR
    if MIN_FRAC * nom1 > floor1:
        floor1 = MIN_FRAC * nom1
    floor2 = HARD_FLOOR
    if MIN_FRAC * nom2 > floor2:
        floor2 = MIN_FRAC * nom2

    if anom1:
        sp1 = max(floor1, sp1 - LOWER_STEP)
    elif sp1 < nom1:
        sp1 = min(nom1, sp1 + RESTORE_STEP)

    if anom2:
        sp2 = max(floor2, sp2 - LOWER_STEP)
    elif sp2 < nom2:
        sp2 = min(nom2, sp2 + RESTORE_STEP)

    diag = ("tank1 anomaly=" + str(anom1) +
            " hot=" + str(c1) + "/" + str(w) +
            " bar=" + str(round(bar1, 4)) +
            " recent|e1|avg=" + str(round(se1 / w, 4)) +
            " pump1_avg=" + str(round(sv1 / w, 2)) + "V; " +
            "tank2 anomaly=" + str(anom2) +
            " hot=" + str(c2) + "/" + str(w) +
            " bar=" + str(round(bar2, 4)) +
            " recent|e2|avg=" + str(round(se2 / w, 4)) +
            " pump2_avg=" + str(round(sv2 / w, 2)) + "V; " +
            "healthy ceilings |e1|max=" + str(E1_MAX) +
            " mean=" + str(E1_MEAN) + ", |e2|max=" + str(E2_MAX) +
            " mean=" + str(E2_MEAN) + ", v1=" + str(V1_MEAN) +
            " v2=" + str(V2_MEAN) + "V (12V rail)")

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": anom1, "tank2": anom2},
    }
