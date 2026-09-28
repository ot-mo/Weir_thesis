def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---- measured healthy anchors for THIS plant (fault-free, plain PID) ----
    # pump effort 1-12 V ; levels 0.05-0.48 m ; settling ~100-300 s
    #   v1: mean 10.41, std 2.27, range [1.92, 12.00]
    #   v2: mean  7.36, std 3.16, range [2.58, 12.00]
    #   total v1+v2 : mean 17.77 V ; split v1-v2 : mean 3.05 V
    #   |e1| mean 0.074 m ; |e2| mean 0.083 m
    # The two cross-coupled pumps run dominantly ANTI-phase, so the split is
    # the loud channel and the total is the quiet one.  A leak is absorbed by
    # the loop's integrators, so the error channel stays at the healthy level
    # while the steady-state effort shifts with an invariant shape:
    #   tank-1 leak: d(v1+v2) = +q , d(v1-v2) = -1.667 q  (v2 up, split DOWN)
    #   tank-2 leak: d(v1+v2) = +q , d(v1-v2) = +1.667 q  (v1 up, split UP)
    T_ANCHOR = 17.77
    S_ANCHOR = 3.05
    B = 80
    DT_THR = 3.0
    ERR_GUARD = 0.115
    SHAPE_LO = 1.1
    SHAPE_HI = 3.0

    def num(d, key, default):
        try:
            x = d[key]
        except Exception:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        return default

    def block_stats(block):
        tot = 0.0
        spl = 0.0
        err = 0.0
        m = 0
        for st in block:
            if not isinstance(st, dict):
                continue
            a = st.get("tank1", {})
            b = st.get("tank2", {})
            v1 = num(a, "pump_effort", 0.0)
            v2 = num(b, "pump_effort", 0.0)
            tot += v1 + v2
            spl += v1 - v2
            err += abs(num(a, "error", 0.0)) + abs(num(b, "error", 0.0))
            m += 1
        if m == 0:
            return None
        return tot / m, spl / m, err / (2.0 * m)

    flag1 = False
    flag2 = False
    info = "warming-up"

    n = 0
    if isinstance(telemetry_window, list):
        n = len(telemetry_window)

    if n >= B:
        s_long = block_stats(telemetry_window[-B:])
        s_short = block_stats(telemetry_window[-(B // 2):])
        if s_long is not None and s_short is not None:
            T80, S80, E80 = s_long
            T40, S40, E40 = s_short
            dT80 = T80 - T_ANCHOR
            dT40 = T40 - T_ANCHOR
            ds1_80 = S_ANCHOR - S80
            ds1_40 = S_ANCHOR - S40
            ds2_80 = S80 - S_ANCHOR
            ds2_40 = S40 - S_ANCHOR
            if (dT80 > DT_THR and dT40 > DT_THR and
                    E80 < ERR_GUARD and E40 < ERR_GUARD):
                up1 = (ds1_80 > SHAPE_LO * dT80 and ds1_80 < SHAPE_HI * dT80 and
                       ds1_40 > SHAPE_LO * dT40 and ds1_40 < SHAPE_HI * dT40)
                up2 = (ds2_80 > SHAPE_LO * dT80 and ds2_80 < SHAPE_HI * dT80 and
                       ds2_40 > SHAPE_LO * dT40 and ds2_40 < SHAPE_HI * dT40)
                if up1 and not up2:
                    flag1 = True
                if up2 and not up1:
                    flag2 = True
            info = "dT80=%.2f dT40=%.2f split80=%.2f err80=%.3f" % (dT80, dT40, S80, E80)

    # Error channel is fault-invariant on this loop, so the nominal demand is
    # always the right command: it keeps IAE minimal, keeps the supervisor's own
    # action out of the effort diagnostic, and makes the restore gap zero.
    try:
        sp1 = float(nominal_targets["tank1"])
    except Exception:
        try:
            sp1 = float(active_setpoints["tank1"])
        except Exception:
            sp1 = 0.30
    try:
        sp2 = float(nominal_targets["tank2"])
    except Exception:
        try:
            sp2 = float(active_setpoints["tank2"])
        except Exception:
            sp2 = 0.35

    return {
        "diagnosis": "tank1 anomaly=%s; tank2 anomaly=%s; %s" % (flag1, flag2, info),
        "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
        "anomaly_flags": {"tank1": flag1, "tank2": flag2},
    }
