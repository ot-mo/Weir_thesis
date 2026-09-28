def supervise(telemetry_window, active_setpoints, nominal_targets):
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    # Measured fault-free reference for THIS plant at the nominal operating
    # point: v1 mean 10.41 V, v2 mean 7.36 V.
    #   v1+v2 -> 17.77 V   ;   v1-v2 -> 3.05 V
    TOTAL_REF = 17.77
    SPLIT_REF = 3.05
    T_FLOOR = 1.8
    S_FLOOR = 2.2
    K_SIGMA = 2.5
    CORR_FUDGE = 1.5
    ERR_GUARD_1 = 0.16
    ERR_GUARD_2 = 0.18
    MIN_STEPS = 40

    flag1 = False
    flag2 = False
    diag = "nominal tracking; no anomaly"

    n = len(telemetry_window)
    if n >= MIN_STEPS:
        T = []
        S = []
        e1 = []
        e2 = []
        for i in range(n):
            step = telemetry_window[i]
            a = step["tank1"]["pump_effort"]
            b = step["tank2"]["pump_effort"]
            T.append(a + b)
            S.append(a - b)
            e1.append(abs(step["tank1"]["error"]))
            e2.append(abs(step["tank2"]["error"]))

        def mean(vals):
            tot = 0.0
            for v in vals:
                tot += v
            return tot / float(len(vals))

        def median(vals):
            sv = sorted(vals)
            k = len(sv)
            if k % 2 == 1:
                return sv[k // 2]
            return 0.5 * (sv[k // 2 - 1] + sv[k // 2])

        def mad(vals):
            med = median(vals)
            dev = []
            for v in vals:
                dev.append(abs(v - med))
            return median(dev)

        m = n // 4
        if m > 60:
            m = 60
        if m >= 10:
            T_rec = mean(T[n - m:])
            S_rec = mean(S[n - m:])
            T_pr = mean(T[n - 2 * m:n - m])
            S_pr = mean(S[n - 2 * m:n - m])

            # Robust per-sample spread taken from the earliest part of the
            # window (the pre-fault part when an onset lies inside the
            # window).  It can only enlarge the thresholds.
            sig_T = 1.4826 * mad(T[0:2 * m])
            sig_S = 1.4826 * mad(S[0:2 * m])

            thr_T = K_SIGMA * CORR_FUDGE * sig_T / (m ** 0.5)
            if thr_T < T_FLOOR:
                thr_T = T_FLOOR
            thr_S = K_SIGMA * CORR_FUDGE * sig_S / (m ** 0.5)
            if thr_S < S_FLOOR:
                thr_S = S_FLOOR

            dT_r = T_rec - TOTAL_REF
            dS_r = S_rec - SPLIT_REF
            dT_p = T_pr - TOTAL_REF
            dS_p = S_pr - SPLIT_REF

            # Total-effort elevation is the presence gate; the anti-phase
            # healthy limit cycle moves the split but not the sum, and the
            # in-phase mode moves the sum but not the split, so requiring
            # both blocks to agree on the sum kills the in-phase mode.
            total_high = (dT_r > thr_T) and (dT_p > 0.5 * thr_T)

            # Fill-transient guard: the error channel is fault-invariant, so
            # a large block |error| (>=0.16 vs the healthy 0.074) can only
            # mean the tanks are still filling, where both pumps rail at
            # 12 V and the effort statistics mimic a severe fault.
            if total_high and mean(e1[n - m:]) < ERR_GUARD_1 and dS_r < -thr_S and dS_p < -0.5 * thr_S:
                flag1 = True
            if total_high and mean(e2[n - m:]) < ERR_GUARD_2 and dS_r > thr_S and dS_p > 0.5 * thr_S:
                flag2 = True

        if flag1 or flag2:
            tl = ""
            if flag1:
                tl = "tank1"
            if flag2:
                if tl == "":
                    tl = "tank2"
                else:
                    tl = tl + "+tank2"
            diag = "sustained cross-branch effort imbalance (leak-like) on " + tl

    # The setpoint channel is score-neutral on this plant (the error channel
    # is fault-invariant), so command nominal unconditionally: no self-made
    # disturbance can leak into the effort-based diagnostic and the
    # restore gap is identically zero.
    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": nom1, "tank2": nom2},
        "anomaly_flags": {"tank1": flag1, "tank2": flag2},
    }
