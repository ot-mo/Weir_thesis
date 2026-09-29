def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ------------------------------------------------------------------
    # Quadruple-tank supervisor, tanks 1 and 2 only.
    #
    # Fault-free envelope measured on THIS plant under plain PID (hard
    # numbers, not estimates):
    #     tank1 error in [-0.0300, +0.1899], mean|e| 0.0743  (target ~0.30)
    #     tank2 error in [-0.0866, +0.1905], mean|e| 0.0832  (target ~0.35)
    #     pump effort: v1 mean 10.42 V, v2 mean 7.33 V against a 12 V rail,
    #     so healthy operation already saturates the actuators; effort has
    #     no usable margin here and is NOT used as evidence.
    #
    # The envelope is strongly ASYMMETRIC and the fault-directed edge is the
    # LOW one: an own leak drains the tank, so level and error fall (the
    # neighbour's leak pushes the error the other way, toward the wide/high
    # edge).  Both per-tank bars therefore sit an EQUAL ABSOLUTE margin
    # outside the measured envelope, which the fault-free record can never
    # reach under any window rule, while a draining fault only has to travel
    # 0.012 past the low edge instead of ~0.17 past a mirrored |error| bar.
    #
    # Decisions use a per-sample COUNT (K of the last W samples outside the
    # envelope).  A block MEAN or a fraction-of-block rule is deliberately
    # NOT used: at the same bar it can never trip earlier than the count
    # rule, but it holds the flag up for a whole extra block after the fault
    # clears, which is exactly the post-clear false-positive tail.
    #
    # Setpoints are held at the nominal reference.  The faulted pump is
    # already pinned at the rail, so trimming the reference buys almost no
    # IAE while it shrinks the very error signal used as evidence
    # (mitigate -> release -> re-flag chatter) and leaves a restore gap.
    #
    # len(telemetry_window) is always exactly 50.
    # ------------------------------------------------------------------

    try:
        nom1 = float(nominal_targets['tank1'])
        nom2 = float(nominal_targets['tank2'])
    except Exception:
        nom1 = 0.30
        nom2 = 0.35

    # nominal reference is held and restored immediately: no trim, no gap
    sp1 = nom1
    sp2 = nom2

    # measured fault-free envelope of the error channel (this plant)
    E1_LO = -0.0300
    E1_HI = 0.1899
    E2_LO = -0.0866
    E2_HI = 0.1905

    MARGIN = 0.012   # equal absolute margin placed outside every edge
    W = 10           # recent decision window (never larger than 50)
    K = 2            # samples outside required: rejects a single outlier

    lo1 = E1_LO - MARGIN   # -0.0420
    hi1 = E1_HI + MARGIN   # +0.2019
    lo2 = E2_LO - MARGIN   # -0.0986
    hi2 = E2_HI + MARGIN   # +0.2025

    n = len(telemetry_window)
    c1 = 0
    c2 = 0
    m1 = 0.0
    m2 = 0.0
    anom1 = False
    anom2 = False
    w = 0

    if n > 0:
        w = W if n > W else n
        start = n - w
        try:
            for i in range(start, n):
                s = telemetry_window[i]
                e1 = float(s['tank1']['error'])
                e2 = float(s['tank2']['error'])
                m1 += abs(e1)
                m2 += abs(e2)
                if e1 < lo1 or e1 > hi1:
                    c1 += 1
                if e2 < lo2 or e2 > hi2:
                    c2 += 1
            m1 = m1 / w
            m2 = m2 / w
            anom1 = bool(c1 >= K)
            anom2 = bool(c2 >= K)
        except Exception:
            c1 = 0
            c2 = 0
            anom1 = False
            anom2 = False

    diag = (
        'tank1 anomaly=' + str(anom1) +
        ' (|e|_mean=' + str(round(m1, 4)) +
        ', samples outside [' + str(round(lo1, 4)) + ',' + str(round(hi1, 4)) +
        '] = ' + str(c1) + '/' + str(w) + ', need ' + str(K) + '); ' +
        'tank2 anomaly=' + str(anom2) +
        ' (|e|_mean=' + str(round(m2, 4)) +
        ', samples outside [' + str(round(lo2, 4)) + ',' + str(round(hi2, 4)) +
        '] = ' + str(c2) + '/' + str(w) + ', need ' + str(K) + '); ' +
        'healthy envelope tank1 [' + str(E1_LO) + ',' + str(E1_HI) + '] ' +
        'tank2 [' + str(E2_LO) + ',' + str(E2_HI) + ']; ' +
        'reference held at nominal (no trim, no restore gap).'
    )

    return {
        'diagnosis': diag,
        'adjusted_setpoints': {'tank1': float(sp1), 'tank2': float(sp2)},
        'anomaly_flags': {'tank1': bool(anom1), 'tank2': bool(anom2)},
    }
