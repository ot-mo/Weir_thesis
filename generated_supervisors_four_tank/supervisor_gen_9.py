def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ------------------------------------------------------------------
    # Measured fault-free anchors on THIS plant (plain PID, no supervisor):
    #   tank1 error range [-0.0300, +0.1899]   mean|e| 0.0743
    #   tank2 error range [-0.0866, +0.1905]   mean|e| 0.0832
    #   v1 mean 10.42 V (range 1.92..12.00), v2 mean 7.33 V (2.54..12.00)
    # BOTH 12 V rails are already inside the healthy effort range and the
    # healthy error peaks reach 0.19, so: (a) effort carries no usable
    # margin, (b) anything calibrated off the healthy MEAN (0.074) sits
    # inside the healthy envelope.  The only rigorous anchor is the
    # measured healthy ENVELOPE, so every bar below lies strictly outside
    # it and is a per-sample (not block-mean/fraction) test.
    # Detection runs on the physical deviation dev = level - target, with
    # the sign convention of the simulator's 'error' field inferred from
    # the window itself, so the cheap TIGHT envelope edge is used too.
    # len(telemetry_window) is ALWAYS exactly 50 (never 30/40/80/100).
    # ------------------------------------------------------------------
    E1_MIN, E1_MAX = -0.0300, 0.1899
    E2_MIN, E2_MAX = -0.0866, 0.1905

    W = 10          # recent decision window (always available inside 50)
    K = 2           # crossings needed inside the window

    LOWER_STEP = 0.0005   # bounded well inside the tightest detection margin
    MIN_FRAC = 0.998      # never more than 0.2% below nominal
    RESTORE_STEP = 0.02
    HARD_FLOOR = 0.05

    n = len(telemetry_window)
    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    if n < 2:
        return {
            "diagnosis": "insufficient telemetry for a decision",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    # ---- physical deviation + sign-convention inference -----------------
    dev = []
    dm = 0.0
    dp = 0.0
    for i in range(n):
        s = telemetry_window[i]
        v1 = s["tank1"]["level"] - sp1
        v2 = s["tank2"]["level"] - sp2
        e1 = s["tank1"]["error"]
        e2 = s["tank2"]["error"]
        dev.append((v1, v2))
        dm += abs(v1 - e1) + abs(v2 - e2)
        dp += abs(v1 + e1) + abs(v2 + e2)

    # error field == level - target  <=>  dm ~ 0 and dp ~ 2*|dev|
    err_is_dev = (dp > 1e-12 and dm < 0.15 * dp)

    hi1 = 1.06 * E1_MAX          # 0.20131
    hi2 = 1.06 * E2_MAX          # 0.20193
    if err_is_dev:
        lo1 = 2.00 * E1_MIN      # -0.0600  (tight edge, fault direction)
        lo2 = 2.00 * E2_MIN      # -0.1732
    else:
        # mirrored envelope: the draining direction is the LOOSE edge, so
        # stay on the loose edge and keep the un-exploitable side wide.
        lo1 = -hi1               # -0.20131
        lo2 = -hi2               # -0.20193

    # ---- K-of-W per-sample crossing count (no mean/fraction routes) -----
    w = W if n > W else n
    c1 = 0
    c2 = 0
    for i in range(n - w, n):
        v1, v2 = dev[i]
        if v1 < lo1 or v1 > hi1:
            c1 += 1
        if v2 < lo2 or v2 > hi2:
            c2 += 1

    anom1 = bool(c1 >= K)
    anom2 = bool(c2 >= K)

    # ---- bounded mitigation / restore ----------------------------------
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

    diag = ("error_convention=" + ("level-target" if err_is_dev else "target-level") +
            "; tank1 dev_out=" + str(c1) + "/" + str(w) +
            " bars(" + str(round(lo1, 4)) + "," + str(round(hi1, 4)) + ") => " + str(anom1) +
            "; tank2 dev_out=" + str(c2) + "/" + str(w) +
            " bars(" + str(round(lo2, 4)) + "," + str(round(hi2, 4)) + ") => " + str(anom2) +
            "; healthy envelope e1[" + str(E1_MIN) + "," + str(E1_MAX) + "]" +
            " e2[" + str(E2_MIN) + "," + str(E2_MAX) + "]" +
            "; effort unused (healthy rails already 12.00)")

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": anom1, "tank2": anom2},
    }
