def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---- external healthy reference: measured fault-free episode, this plant ----
    # pump effort is in volts (1-12 V rail); these are hard measured numbers.
    REF_V1 = 10.41        # healthy mean pump-1 effort (V)
    REF_V2 = 7.36         # healthy mean pump-2 effort (V)
    REF_SUM = REF_V1 + REF_V2      # 17.77 V total
    REF_DIFF = REF_V1 - REF_V2     # 3.05 V (healthy pump1 carries more)
    SD1 = 2.27            # healthy pump-1 effort std (V)
    SD2 = 3.16            # healthy pump-2 effort std (V)

    n = len(telemetry_window)
    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    flag1 = False
    flag2 = False
    diag = "no anomaly"

    if n >= 4:
        v1 = [step["tank1"]["pump_effort"] for step in telemetry_window]
        v2 = [step["tank2"]["pump_effort"] for step in telemetry_window]

        m1 = sum(v1) / n
        m2 = sum(v2) / n

        # Total effort above the healthy operating point.  A leak on EITHER
        # branch forces extra total flow, so this rises in proportion to the
        # total leak size and does not depend on which branch is faulted.
        E = (m1 + m2) - REF_SUM

        # Cross-branch load shift.  >0 : pump 2 is carrying more than its
        # healthy share of the delayed cross path  -> TANK-1 fault.
        # <0 : pump 1 is carrying more            -> TANK-2 fault.
        # ~0 with E>0                              -> symmetric double fault.
        S = (m2 - m1) + REF_DIFF

        # Window-mean standard error, discounted for autocorrelation of the
        # slow (100-300 s) cross-coupled oscillation.
        n_eff = max(4, n // 3)
        se = math.sqrt(SD1 * SD1 + SD2 * SD2) / math.sqrt(n_eff)

        T_E = max(1.5, 2.0 * se)
        T_S = max(0.8, 0.4 * T_E)

        # Persistence: most individual samples must themselves sit above the
        # healthy total, so two oscillatory outliers cannot carry the mean.
        above = 0
        for i in range(n):
            if v1[i] + v2[i] > REF_SUM:
                above += 1

        if E > T_E and above >= 0.65 * n:
            if S > T_S:
                flag1 = True
                diag = "tank1 anomaly: cross-path load shifted onto pump2"
            elif S < -T_S:
                flag2 = True
                diag = "tank2 anomaly: cross-path load shifted onto pump1"
            else:
                flag1 = True
                flag2 = True
                diag = "symmetric total-effort rise: both branches faulted"

    # ---- setpoint policy -------------------------------------------------
    # The tracking-error channel is fault-invariant here, so lowering a demand
    # cannot improve IAE and only risks a restore gap.  Never lower; ramp an
    # already-lowered demand gently back toward nominal when not flagged.
    def restore(sp, nom, flagged):
        sp = float(sp)
        nom = float(nom)
        if flagged:
            return sp
        if sp < nom:
            return min(nom, sp + 0.005)
        if sp > nom:
            return max(nom, sp - 0.005)
        return sp

    new1 = restore(sp1, nom1, flag1)
    new2 = restore(sp2, nom2, flag2)

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": round(new1, 4), "tank2": round(new2, 4)},
        "anomaly_flags": {"tank1": flag1, "tank2": flag2},
    }
