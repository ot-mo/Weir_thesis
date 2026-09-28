def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---- measured healthy (fault-free, plain PID) anchors for THIS plant ----
    # v1: mean 10.42 V (std 2.27, range 1.92-12.00); v2: mean 7.33 V (std 3.16, 2.54-12.00)
    # tank1 mean|error| 0.0743 (range -0.030..0.190); tank2 mean|error| 0.0832 (-0.087..0.191)
    V1_ANCHOR = 10.42
    V2_ANCHOR = 7.33

    n = len(telemetry_window)
    if n < 4:
        return {
            "diagnosis": "telemetry too short for a block decision",
            "adjusted_setpoints": {
                "tank1": float(active_setpoints["tank1"]),
                "tank2": float(active_setpoints["tank2"]),
            },
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    # recent decision window: <= 20 samples, always <= 50
    R = min(20, n)
    if R < 1:
        R = 1

    # ---- gates, all relative to the measured healthy envelope ----
    # recent/full block-mean |error| gates (~1.8x / ~1.3x the healthy mean|error|)
    E1_R = 0.13
    E1_F = 0.10
    E2_R = 0.14
    E2_F = 0.11
    # clearly anomalous on its own: above the largest measured instantaneous |error| (0.19)
    E_STRONG = 0.21
    # pump effort must have left its healthy band (either rail), small margin
    V_MAR1 = 0.80
    V_MAR2 = 1.00

    def block(lo, hi):
        cnt = hi - lo
        a1 = 0.0
        a2 = 0.0
        e1 = 0.0
        e2 = 0.0
        for i in range(lo, hi):
            s = telemetry_window[i]
            a1 += s["tank1"]["pump_effort"]
            a2 += s["tank2"]["pump_effort"]
            e1 += abs(s["tank1"]["error"])
            e2 += abs(s["tank2"]["error"])
        return a1 / cnt, a2 / cnt, e1 / cnt, e2 / cnt

    v1f, v2f, e1f, e2f = block(0, n)
    v1r, v2r, e1r, e2r = block(n - R, n)

    # sustained tracking error on each tank's OWN loop
    tank1_err = bool(e1r > E1_R and e1f > E1_F)
    tank2_err = bool(e2r > E2_R and e2f > E2_F)

    # the tank's own pump has left its healthy operating band (leak pulls up, overflow pulls down)
    tank1_eff = bool(abs(v1r - V1_ANCHOR) > V_MAR1)
    tank2_eff = bool(abs(v2r - V2_ANCHOR) > V_MAR2)

    # flag only when the tank's own error is sustained AND its own loop is stressed,
    # or the error is unambiguously huge on its own
    tank1_anomaly = bool(tank1_err and (tank1_eff or e1r > E_STRONG))
    tank2_anomaly = bool(tank2_err and (tank2_eff or e2r > E_STRONG))

    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    LOWER_STEP = 0.015
    RESTORE_STEP = 0.030
    floor1 = max(0.12, 0.5 * nom1)
    floor2 = max(0.12, 0.5 * nom2)

    if tank1_anomaly:
        sp1 = max(floor1, sp1 - LOWER_STEP)
    elif sp1 < nom1:
        sp1 = min(nom1, sp1 + RESTORE_STEP)

    if tank2_anomaly:
        sp2 = max(floor2, sp2 - LOWER_STEP)
    elif sp2 < nom2:
        sp2 = min(nom2, sp2 + RESTORE_STEP)

    diag = ("tank1 anomaly=" + str(tank1_anomaly) +
            " (e_r=" + str(round(e1r, 3)) + ", e_f=" + str(round(e1f, 3)) +
            ", v1_r=" + str(round(v1r, 2)) + "V); " +
            "tank2 anomaly=" + str(tank2_anomaly) +
            " (e_r=" + str(round(e2r, 3)) + ", e_f=" + str(round(e2f, 3)) +
            ", v2_r=" + str(round(v2r, 2)) + "V)")

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
