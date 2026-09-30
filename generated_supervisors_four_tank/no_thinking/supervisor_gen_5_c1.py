def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    if n == 0:
        return {
            "diagnosis": "empty window",
            "adjusted_setpoints": {"tank1": active_setpoints["tank1"], "tank2": active_setpoints["tank2"]},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    def mean(vals):
        return sum(vals) / float(len(vals)) if vals else 0.0

    eff1 = [s["tank1"]["pump_effort"] for s in telemetry_window]
    eff2 = [s["tank2"]["pump_effort"] for s in telemetry_window]
    lvl1 = [s["tank1"]["level"] for s in telemetry_window]
    lvl2 = [s["tank2"]["level"] for s in telemetry_window]

    m1 = mean(eff1[-10:])
    m2 = mean(eff2[-10:])
    l1 = lvl1[-1]
    l2 = lvl2[-1]

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    err1 = sp1 - l1
    err2 = sp2 - l2

    # thresholds (V) chosen above healthy settled maxima (t1 10.54, t2 9.26)
    E1_ON = 10.7
    E2_ON = 9.5
    E1_OFF = 10.2
    E2_OFF = 9.1
    BASE_GAP = 0.45

    base1 = mean(eff1[:10])
    base2 = mean(eff2[:10])

    def tail_ok(series, thresh, k, above):
        if len(series) < k:
            return False
        seg = series[-k:]
        for v in seg:
            if above and v < thresh:
                return False
            if (not above) and v > thresh:
                return False
        return True

    sig1 = m1 > E1_ON and m1 > base1 + BASE_GAP and err1 > 0.01
    sig2 = m2 > E2_ON and m2 > base2 + BASE_GAP and err2 > 0.01

    enter1 = sig1 and tail_ok(eff1, E1_ON, 4, True) and tail_ok(lvl1, sp1 - 0.05, 4, False)
    enter2 = sig2 and tail_ok(eff2, E2_ON, 4, True) and tail_ok(lvl2, sp2 - 0.05, 4, False)

    clear1 = (m1 < E1_OFF) and (err1 < 0.02)
    clear2 = (m2 < E2_OFF) and (err2 < 0.02)

    trimmed1 = sp1 < nom1 - 1e-9
    trimmed2 = sp2 < nom2 - 1e-9

    flag1 = False
    flag2 = False

    if enter1:
        flag1 = True
    elif trimmed1:
        flag1 = not clear1

    if enter2:
        flag2 = True
    elif trimmed2:
        flag2 = not clear2

    LOWER = 0.02
    RESTORE = 0.02

    if flag1:
        new1 = max(0.05, sp1 - LOWER)
    elif sp1 < nom1 - 1e-9:
        new1 = min(nom1, sp1 + RESTORE)
    else:
        new1 = sp1

    if flag2:
        new2 = max(0.05, sp2 - LOWER)
    elif sp2 < nom2 - 1e-9:
        new2 = min(nom2, sp2 + RESTORE)
    else:
        new2 = sp2

    return {
        "diagnosis": "tank1 flag=%s m=%.2f b=%.2f e=%.3f; tank2 flag=%s m=%.2f b=%.2f e=%.3f" % (
            flag1, m1, base1, err1, flag2, m2, base2, err2),
        "adjusted_setpoints": {"tank1": new1, "tank2": new2},
        "anomaly_flags": {"tank1": flag1, "tank2": flag2},
    }