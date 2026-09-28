def supervise(telemetry_window, active_setpoints, nominal_targets):
    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    n = len(telemetry_window)
    if n < 2 or nom1 <= 0.0 or nom2 <= 0.0:
        return {
            "diagnosis": "insufficient telemetry; no action",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    lev1 = [float(step["tank1"]["level"]) for step in telemetry_window]
    lev2 = [float(step["tank2"]["level"]) for step in telemetry_window]
    eff1 = [float(step["tank1"]["pump_effort"]) for step in telemetry_window]
    eff2 = [float(step["tank2"]["pump_effort"]) for step in telemetry_window]
    err1 = [float(step["tank1"]["error"]) for step in telemetry_window]
    err2 = [float(step["tank2"]["error"]) for step in telemetry_window]

    EPS = 1e-9
    GAMMA = 0.2

    # Window-independent healthy reference: steady-state mass balance of the
    # four-tank plant at the nominal operating point. This is valid even when
    # a persistent fault is already active at the start of the window.
    u1n = max(nom1, EPS) ** 0.5
    u2n = max(nom2, EPS) ** 0.5
    det = 2.0 * GAMMA - 1.0
    if abs(det) < 1e-6:
        sym0 = 0.0
    else:
        v1n = (GAMMA * u1n - (1.0 - GAMMA) * u2n) / det
        v2n = (GAMMA * u2n - (1.0 - GAMMA) * u1n) / det
        s1n = v1n / u1n
        s2n = v2n / u2n
        sym0 = (s1n - s2n) / (s1n + s2n + EPS)

    SYM_TH = 0.08
    DEF_TH = 0.07
    BIAS_TH = 0.6
    ERR_TH = 0.15

    def signals(a, b):
        m = b - a
        if m <= 0:
            return None
        L1 = sum(lev1[a:b]) / m
        L2 = sum(lev2[a:b]) / m
        E1 = sum(eff1[a:b]) / m
        E2 = sum(eff2[a:b]) / m
        se1 = E1 / (max(L1, EPS) ** 0.5)
        se2 = E2 / (max(L2, EPS) ** 0.5)
        sym = (se1 - se2) / (se1 + se2 + EPS)
        dev = sym - sym0
        d1 = (nom1 - L1) / nom1
        d2 = (nom2 - L2) / nom2
        AE1 = sum(abs(x) for x in err1[a:b]) / m
        AE2 = sum(abs(x) for x in err2[a:b]) / m
        ME1 = sum(err1[a:b]) / m
        ME2 = sum(err2[a:b]) / m
        b1 = abs(ME1) / (AE1 + EPS)
        b2 = abs(ME2) / (AE2 + EPS)
        r1 = AE1 / nom1
        r2 = AE2 / nom2
        return dev, d1, d2, b1, b2, r1, r2

    def judge(sig):
        if sig is None:
            return False, False
        dev, d1, d2, b1, b2, r1, r2 = sig
        # directional twin-reference signal: only the branch whose own
        # specific effort rises can be flagged.
        a1 = dev > SYM_TH
        a2 = dev < -SYM_TH
        # external absolute reference: head sagging below nominal target.
        if d1 > DEF_TH:
            a1 = True
        if d2 > DEF_TH:
            a2 = True
        # strict conjunction of error magnitude and error one-sidedness.
        if b1 > BIAS_TH and r1 > ERR_TH:
            a1 = True
        if b2 > BIAS_TH and r2 > ERR_TH:
            a2 = True
        return a1, a2

    f1, f2 = judge(signals(0, n))
    m = max(3, n // 2)
    g1, g2 = judge(signals(max(0, n - m), n))

    tank1_anomaly = bool(f1 and g1)
    tank2_anomaly = bool(f2 and g2)

    # Bounded, monotone setpoint policy. Reduction (3% of nominal) is kept
    # well below the deficit threshold so the supervisor's own action can
    # never re-trigger the detector.
    LOWER_FRAC = 0.03
    RESTORE_STEP = 0.01

    def adjust(sp, nom, anomaly):
        if anomaly:
            lo = nom * (1.0 - LOWER_FRAC)
            return min(sp, lo)
        if sp < nom - 1e-9:
            return min(nom, sp + RESTORE_STEP)
        return sp

    new_sp1 = adjust(sp1, nom1, tank1_anomaly)
    new_sp2 = adjust(sp2, nom2, tank2_anomaly)

    diagnosis = (
        "tank1 anomaly=" + str(tank1_anomaly)
        + " sp " + str(round(new_sp1, 4))
        + "; tank2 anomaly=" + str(tank2_anomaly)
        + " sp " + str(round(new_sp2, 4))
    )

    return {
        "diagnosis": diagnosis,
        "adjusted_setpoints": {"tank1": float(new_sp1), "tank2": float(new_sp2)},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
