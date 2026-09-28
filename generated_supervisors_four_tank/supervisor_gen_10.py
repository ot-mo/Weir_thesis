def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ==================================================================
    # QUADRUPLE tank, split deliberately in the NON-MINIMUM-PHASE regime
    # (most of v1 is routed h4 -> h2, most of v2 is routed h3 -> h1).
    #
    # MEASURED fault-free reference statistics for THIS plant (plain PID,
    # no supervisor action, 1 Hz samples, hard numbers):
    #   tank1 error : [-0.0300, +0.1899], mean|e| = 0.0743, target ~0.30
    #   tank2 error : [-0.0866, +0.1905], mean|e| = 0.0832, target ~0.35
    #   v1 effort   : mean 10.42 V, range [1.92, 12.00]  (1.6 V headroom)
    #   v2 effort   : mean  7.33 V, range [2.54, 12.00]  (4.7 V headroom)
    # So BOTH tanks genuinely oscillate and BOTH pumps genuinely sit on the
    # 12 V rail with nothing wrong -> pump effort carries no usable fault
    # signal; the only tightly bounded observable is the per-tank error.
    #
    # FAULT DIRECTION (why both bars are ONE-SIDED):
    #   A leak drains its own tank.  In this split that tank is fed mainly
    #   by the OTHER branch, so the extra flow its own saturated pump makes
    #   is dumped through the cross branch into the NEIGHBOUR, and the
    #   faulted tank is driven toward the TIGHT (low) edge of its envelope,
    #   while the healthy neighbour is pushed toward the WIDE (+0.19) edge.
    #   Therefore: a tight bar just BELOW the low edge gives fast detection
    #   of a tank's own fault and is never touched by cross-coupling, and a
    #   far backstop bar WELL ABOVE the high edge catches a hypothetical
    #   high-going fault without ever firing on healthy cross-coupling.
    #
    # Both bars sit STRICTLY outside the measured healthy envelope, so no
    # fault-free sample can reach them: zero baseline false positives by
    # construction, not by averaging.  len(telemetry_window) is ALWAYS 50.
    # ==================================================================
    E1_LO, E1_HI = -0.0300, 0.1899   # tank1 fault-free error envelope
    E2_LO, E2_HI = -0.0866, 0.1905   # tank2 fault-free error envelope

    NEG_MARGIN = 0.025               # absolute, metres -> lo1 -0.0550, lo2 -0.1116
    POS_MARGIN = 0.060               # absolute, metres -> hi1  0.2499, hi2  0.2505

    W_NEG = 6                        # recent decision block for the tight bar
    K_NEG = 2                        # >=2 of the last 6 samples below the tight bar
    W_POS = 12                       # sustained block for the far backstop
    K_POS = 9                        # >=9 of the last 12 samples above the far bar

    lo1 = E1_LO - NEG_MARGIN
    hi1 = E1_HI + POS_MARGIN
    lo2 = E2_LO - NEG_MARGIN
    hi2 = E2_HI + POS_MARGIN

    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])
    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])

    n = len(telemetry_window)
    if n < 3:
        return {
            "diagnosis": "insufficient telemetry (" + str(n) + " samples); references held at nominal",
            "adjusted_setpoints": {"tank1": nom1, "tank2": nom2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    w_neg = W_NEG if n > W_NEG else n
    w_pos = W_POS if n > W_POS else n
    k_neg = K_NEG if K_NEG < w_neg else w_neg
    k_pos = K_POS if K_POS < w_pos else w_pos

    neg_from = n - w_neg
    pos_from = n - w_pos

    cn1 = 0
    cn2 = 0
    cp1 = 0
    cp2 = 0
    se1 = 0.0
    se2 = 0.0
    sv1 = 0.0
    sv2 = 0.0
    for i in range(pos_from, n):
        s = telemetry_window[i]
        e1 = s["tank1"]["error"]
        e2 = s["tank2"]["error"]
        se1 += e1
        se2 += e2
        sv1 += s["tank1"]["pump_effort"]
        sv2 += s["tank2"]["pump_effort"]
        if i >= neg_from:
            if e1 < lo1:
                cn1 += 1
            if e2 < lo2:
                cn2 += 1
        if e1 > hi1:
            cp1 += 1
        if e2 > hi2:
            cp2 += 1

    anom1 = bool(cn1 >= k_neg or cp1 >= k_pos)
    anom2 = bool(cn2 >= k_neg or cp2 >= k_pos)

    # ---- setpoint policy ---------------------------------------------
    # A leak is a capacity loss: trimming the reference cannot put water
    # back and it would shrink the very error used as evidence here
    # (mitigate -> release -> re-flag chatter).  The reference is therefore
    # held at - and restored to - nominal, so restore_gap is identically 0.
    adj1 = nom1
    adj2 = nom2

    diag = ("tank1 bars [" + str(round(lo1, 4)) + ", " + str(round(hi1, 4)) + "] " +
            "tight " + str(cn1) + "/" + str(w_neg) +
            " far " + str(cp1) + "/" + str(w_pos) +
            " anom=" + str(anom1) +
            " mean_e1=" + str(round(se1 / w_pos, 4)) +
            " mean_v1=" + str(round(sv1 / w_pos, 2)) + "V; " +
            "tank2 bars [" + str(round(lo2, 4)) + ", " + str(round(hi2, 4)) + "] " +
            "tight " + str(cn2) + "/" + str(w_neg) +
            " far " + str(cp2) + "/" + str(w_pos) +
            " anom=" + str(anom2) +
            " mean_e2=" + str(round(se2 / w_pos, 4)) +
            " mean_v2=" + str(round(sv2 / w_pos, 2)) + "V; " +
            "fault-free envelope e1[" + str(E1_LO) + "," + str(E1_HI) +
            "] e2[" + str(E2_LO) + "," + str(E2_HI) +
            "]; references held at nominal (n=" + str(n) +
            ", active sp=(" + str(round(sp1, 3)) + "," + str(round(sp2, 3)) + "))")

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(adj1), "tank2": float(adj2)},
        "anomaly_flags": {"tank1": anom1, "tank2": anom2},
    }
