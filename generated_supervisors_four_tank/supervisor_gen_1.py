def supervise(telemetry_window, active_setpoints, nominal_targets):
    # Healthy, fault-free anchors measured on a real PID episode
    TOT_ANCHOR = 17.77      # mean(v1 + v2) [V]
    SPLIT_ANCHOR = 3.05     # mean(v1 - v2) [V]

    # ---- directional detector ----
    # h1 loop is paired with v1, h2 with v2.
    # tank1 leak -> v1 up -> split rises (dS > 0)
    # tank2 leak -> v2 up -> split falls (dS < 0)
    DT_GATE = 2.8
    LO = 1.30
    HI = 2.60
    DT_GATE_REC = 2.2
    LO_R = 1.05
    HI_R = 3.20

    # ---- symmetric overload fallback (both pumps up, split near anchor) ----
    DT_BOTH = 3.2
    DT_BOTH_REC = 2.4
    DS_FRAC = 0.60
    ERR_BOTH = 0.14

    LOWER_STEP = 0.02
    RESTORE_STEP = 0.03

    n = len(telemetry_window)
    if n < 6:
        return {
            "diagnosis": "telemetry too short for a block decision",
            "adjusted_setpoints": {
                "tank1": float(active_setpoints["tank1"]),
                "tank2": float(active_setpoints["tank2"]),
            },
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    def block(lo, hi):
        cnt = hi - lo
        tot = 0.0
        spl = 0.0
        e1 = 0.0
        e2 = 0.0
        for i in range(lo, hi):
            s = telemetry_window[i]
            a = s["tank1"]["pump_effort"]
            b = s["tank2"]["pump_effort"]
            tot += a + b
            spl += a - b
            e1 += abs(s["tank1"]["error"])
            e2 += abs(s["tank2"]["error"])
        return tot / cnt, spl / cnt, e1 / cnt, e2 / cnt

    half = n // 2
    mT, mS, me1, me2 = block(0, n)
    rT, rS, re1, re2 = block(n - half, n)

    dT = mT - TOT_ANCHOR
    dS = mS - SPLIT_ANCHOR
    dTr = rT - TOT_ANCHOR
    dSr = rS - SPLIT_ANCHOR

    # tank-1 leak: total up, split pushed UP (v1 over-pumping)
    tank1_full = bool(dT > DT_GATE and dS > LO * dT and dS < HI * dT)
    # tank-2 leak: mirrored (v2 over-pumping pushes split DOWN)
    tank2_full = bool(dT > DT_GATE and dS < -LO * dT and dS > -HI * dT)
    tank1_rec = bool(dTr > DT_GATE_REC and dSr > LO_R * dTr and dSr < HI_R * dTr)
    tank2_rec = bool(dTr > DT_GATE_REC and dSr < -LO_R * dTr and dSr > -HI_R * dTr)

    tank1_anomaly = bool(tank1_full and tank1_rec)
    tank2_anomaly = bool(tank2_full and tank2_rec)

    # symmetric both-pump overload: total high, split near its anchor,
    # and both tracking errors clearly above the healthy envelope
    both_full = bool(dT > DT_BOTH and abs(dS) < DS_FRAC * dT
                     and me1 > ERR_BOTH and me2 > ERR_BOTH)
    both_rec = bool(dTr > DT_BOTH_REC and abs(dSr) < DS_FRAC * dTr
                    and re1 > ERR_BOTH and re2 > ERR_BOTH)
    if both_full and both_rec:
        tank1_anomaly = True
        tank2_anomaly = True

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    if tank1_anomaly:
        sp1 = max(0.05, sp1 - LOWER_STEP)
    elif sp1 < nom1:
        sp1 = min(nom1, sp1 + RESTORE_STEP)

    if tank2_anomaly:
        sp2 = max(0.05, sp2 - LOWER_STEP)
    elif sp2 < nom2:
        sp2 = min(nom2, sp2 + RESTORE_STEP)

    diag = ("tank1 anomaly=" + str(tank1_anomaly) +
            " (dT=" + str(round(dT, 2)) + "V, dS=" + str(round(dS, 2)) + "V); " +
            "tank2 anomaly=" + str(tank2_anomaly) +
            " (dT=" + str(round(dTr, 2)) + "V, dS=" + str(round(dSr, 2)) + "V)")

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(sp1), "tank2": float(sp2)},
        "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
    }
