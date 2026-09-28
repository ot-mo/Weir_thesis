def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---- External anchors measured on the fault-free healthy episode ----
    TOTAL0 = 17.77      # healthy mean(v1 + v2), volts
    SPLIT0 = 3.05       # healthy mean(v1 - v2), volts

    DT_THR    = 2.5     # total-effort excess (volts) needed to consider a leak
    SHAPE_LO  = 0.6     # |ds|/dt lower edge (double-rail saturation sits at 0.49)
    SHAPE_HI  = 5.0     # |ds|/dt upper edge (pure anti-phase swing -> very large)
    SYM_THR   = 3.5     # total excess for a symmetric (both-branch) leak
    ERR_GUARD = 0.115   # suppress the fill-transient regime (block-mean |error| ~0.25)
    B         = 100     # trailing analysis block (samples)
    MIN_N     = 80      # do not judge a block that is mostly episode-start fill

    n = len(telemetry_window)

    def _nominal():
        return {"tank1": nominal_targets["tank1"],
                "tank2": nominal_targets["tank2"]}

    if n == 0:
        return {
            "diagnosis": "no telemetry",
            "adjusted_setpoints": _nominal(),
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    block = telemetry_window[-B:] if n > B else telemetry_window
    m = len(block)

    tot = 0.0
    spl = 0.0
    err = 0.0
    for step in block:
        e1 = step["tank1"]["pump_effort"]
        e2 = step["tank2"]["pump_effort"]
        tot += e1 + e2
        spl += e1 - e2
        err += abs(step["tank1"]["error"]) + abs(step["tank2"]["error"])
    tot /= m
    spl /= m
    mean_abs_err = err / (2.0 * m)

    dt = tot - TOTAL0
    ds = spl - SPLIT0

    ready = (n >= MIN_N) and (mean_abs_err < ERR_GUARD)

    f1 = False
    f2 = False
    if ready and dt > DT_THR:
        # Leak shape: a tank-1 leak raises the total by q and lowers the split
        # by 1.667*q (mirror for tank-2), so the split must move OPPOSITE to
        # the total with 0.6 <= |ds|/dt <= 5. Healthy anti-phase swing keeps
        # the total flat; healthy in-phase swing keeps the split flat.
        if (-SHAPE_HI * dt) < ds < (-SHAPE_LO * dt):
            f1 = True
        elif (SHAPE_LO * dt) < ds < (SHAPE_HI * dt):
            f2 = True
        elif dt > SYM_THR and abs(ds) < (SHAPE_LO * dt):
            # symmetric leak: total doubled, split untouched
            f1 = True
            f2 = True

    if f1 and f2:
        diag = "symmetric pump-effort excess on both branches"
    elif f1:
        diag = "tank1 branch effort excess (possible tank1 leak)"
    elif f2:
        diag = "tank2 branch effort excess (possible tank2 leak)"
    else:
        diag = "no anomaly"

    return {
        "diagnosis": diag,
        "adjusted_setpoints": _nominal(),
        "anomaly_flags": {"tank1": f1, "tank2": f2},
    }
