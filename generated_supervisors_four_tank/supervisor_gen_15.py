def supervise(telemetry_window, active_setpoints, nominal_targets):
    """Deterministic supervisor for the quadruple-tank (Johansson) benchmark.

    Healthy-plant anchors, measured on a fault-free episode under plain PID
    at the nominal setpoints (the supervisor never moves the setpoints, so
    its own commands cannot contaminate the telemetry):
        pump1 effort : mean 10.41 V, sd 2.27, range [1.92, 12.00] V
        pump2 effort : mean  7.36 V, sd 3.16, range [2.58, 12.00] V
        total v1+v2  : 17.77 V
        split v1-v2  :  3.05 V
        mean|error|  : 0.0740 (tank1), 0.0832 (tank2)

    The healthy loop only oscillates because of the non-minimum-phase
    cross-coupling, and that oscillation is dominantly ANTI-phase: the
    split swings while the total stays put.  Extra outflow (a leak) is
    in-phase in the total and displaces the split with a fixed shape
    |d_split| = 1.667 * d_total.  Everything below is therefore tested on
    block means of the total and the split, never on single samples.
    """

    # ---- external anchors and gates (volts / metres) --------------------
    TOTAL_ANCHOR = 17.77     # healthy mean of v1+v2
    SPLIT_ANCHOR = 3.05      # healthy mean of v1-v2
    DT_GATE = 2.90           # required block-mean total excess (T > 20.67 V)
    RATIO_LO = 0.75          # |split displacement| / total excess band
    RATIO_HI = 2.50          # (leak steady state gives exactly 1.667)
    SAME_SIDE_MIN = 0.50     # recent-half split displacement must exceed this
    ERR_GUARD = 0.105        # mean|error| above this is the start-up fill
    PIN_VETO = 9.50          # both pumps pinned this high is the fill
    HALF_MIN = 20            # minimum samples before any decision

    def _nom(key, fallback):
        try:
            v = float(nominal_targets[key])
            if v == v:
                return v
        except Exception:
            pass
        return fallback

    sp1 = _nom("tank1", 0.30)
    sp2 = _nom("tank2", 0.35)

    out = {
        "diagnosis": "nominal operation: no anomaly detected",
        "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
        "anomaly_flags": {"tank1": False, "tank2": False},
    }

    try:
        n = len(telemetry_window)
        if n < HALF_MIN:
            out["diagnosis"] = "warming up: too few samples, no flags"
            return out

        B = 100 if n >= 100 else n
        seg = telemetry_window[n - B:n]
        h = B // 2

        def _block(rows):
            m = len(rows)
            a = 0.0
            b = 0.0
            q1 = 0.0
            q2 = 0.0
            lo1 = None
            lo2 = None
            for r in rows:
                r1 = r["tank1"]
                r2 = r["tank2"]
                x1 = float(r1["pump_effort"])
                x2 = float(r2["pump_effort"])
                a += x1
                b += x2
                q1 += abs(float(r1["error"]))
                q2 += abs(float(r2["error"]))
                if lo1 is None or x1 < lo1:
                    lo1 = x1
                if lo2 is None or x2 < lo2:
                    lo2 = x2
            return (a / m, b / m, q1 / m, q2 / m, lo1, lo2)

        v1f, v2f, e1f, e2f, lo1, lo2 = _block(seg)
        v1h, v2h, e1h, e2h, _, _ = _block(seg[h:])

        dT = (v1f + v2f) - TOTAL_ANCHOR
        dS = (v1f - v2f) - SPLIT_ANCHOR
        dTh = (v1h + v2h) - TOTAL_ANCHOR
        dSh = (v1h - v2h) - SPLIT_ANCHOR

        err_block = 0.5 * (e1f + e2f)
        err_recent = 0.5 * (e1h + e2h)

        # the start-up fill raises the total to the rails while both levels
        # are far below target: block-mean |error| ~0.25 m versus 0.074-0.083
        # healthy, and both pumps sit pinned near 12 V.
        quiet = (err_block < ERR_GUARD) and (err_recent < ERR_GUARD)
        pinned = (lo1 > PIN_VETO) and (lo2 > PIN_VETO)

        fired = False
        if quiet and (not pinned) and dT > DT_GATE and dTh > DT_GATE:
            ratio = abs(dS) / dT
            if RATIO_LO <= ratio <= RATIO_HI:
                if dS < 0.0:
                    # tank1 leak: its own pump throttles back, the
                    # cross-coupled pump2 carries the load -> split drops
                    if dSh < -SAME_SIDE_MIN:
                        out["anomaly_flags"]["tank1"] = True
                        fired = True
                elif dS > 0.0:
                    if dSh > SAME_SIDE_MIN:
                        out["anomaly_flags"]["tank2"] = True
                        fired = True

        if fired:
            f1 = out["anomaly_flags"]["tank1"]
            f2 = out["anomaly_flags"]["tank2"]
            if f1 and f2:
                who = "tank1+tank2"
            elif f1:
                who = "tank1"
            else:
                who = "tank2"
            out["diagnosis"] = (
                "abnormal outflow on %s: block-mean total effort %.2f V "
                "(healthy 17.77), split %.2f V (healthy 3.05), mean|err| %.3f m"
                % (who, v1f + v2f, v1f - v2f, err_block)
            )
        else:
            out["diagnosis"] = (
                "nominal operation: total %.2f V, split %.2f V, mean|err| %.3f m"
                % (v1f + v2f, v1f - v2f, err_block)
            )
        return out
    except Exception:
        return {
            "diagnosis": "internal guard: no flags issued",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }
