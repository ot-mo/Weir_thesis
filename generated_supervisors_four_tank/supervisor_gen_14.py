def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---- measured fault-free anchors for THIS plant (Johansson four-tank) ----
    TOTAL_ANCHOR = 17.77   # mean(v1 + v2) on a healthy episode, volts
    SPLIT_ANCHOR = 3.05    # mean(v1 - v2) on a healthy episode, volts

    # ---- gates, all expressed relative to the anchors above ----
    DT_THR = 3.0        # block-mean total excess needed before a fault is even considered
    DT_SYM = 4.2        # stricter bar for the undirected (balanced double-leak) branch
    ERR_GUARD = 0.12    # block-mean |error| above this => start-up fill transient
    SHAPE_LO = 0.6      # |split deviation| / total excess, lower edge (nominal leak shape 1.667)
    SHAPE_HI = 5.0      # upper edge
    SYM_TOL = 1.0       # |split deviation| that still counts as "split undisplaced"
    BLOCK_MAX = 80      # trailing averaging block (latency/FP dial)

    nominal1 = float(nominal_targets["tank1"])
    nominal2 = float(nominal_targets["tank2"])
    out_setpoints = {"tank1": nominal1, "tank2": nominal2}

    n = len(telemetry_window)
    if n < 20:
        return {
            "diagnosis": "normal: insufficient telemetry, nominal setpoints held",
            "adjusted_setpoints": out_setpoints,
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    total = []
    split = []
    ae1 = []
    ae2 = []
    for step in telemetry_window:
        e1 = step["tank1"]["pump_effort"]
        e2 = step["tank2"]["pump_effort"]
        total.append(e1 + e2)
        split.append(e1 - e2)
        ae1.append(abs(step["tank1"]["error"]))
        ae2.append(abs(step["tank2"]["error"]))

    B = min(n, BLOCK_MAX)
    H = max(1, B // 2)

    def tail_mean(xs, k):
        s = 0.0
        for i in range(n - k, n):
            s += xs[i]
        return s / float(k)

    dt = tail_mean(total, B) - TOTAL_ANCHOR
    ds = tail_mean(split, B) - SPLIT_ANCHOR
    dt_recent = tail_mean(total, H) - TOTAL_ANCHOR

    err_block = tail_mean(ae1, B)
    e2b = tail_mean(ae2, B)
    if e2b > err_block:
        err_block = e2b

    fill_guard = err_block > ERR_GUARD

    flag1 = False
    flag2 = False
    if (not fill_guard) and (dt >= DT_THR) and (dt_recent >= DT_THR):
        # directional localiser 1: split displaced toward the tank-1 signature
        if ds <= -SHAPE_LO * dt and ds >= -SHAPE_HI * dt:
            flag1 = True
        # directional localiser 2: mirrored signature for tank 2
        if ds >= SHAPE_LO * dt and ds <= SHAPE_HI * dt:
            flag2 = True
        # undirected branch: total up, split essentially undisplaced
        if abs(ds) <= SYM_TOL and dt >= DT_SYM:
            flag1 = True
            flag2 = True

    if flag1 and flag2:
        diag = "anomaly: total effort excess with split undisplaced (both branches)"
    elif flag1:
        diag = "anomaly: tank1 branch leak signature"
    elif flag2:
        diag = "anomaly: tank2 branch leak signature"
    elif fill_guard:
        diag = "normal: start-up fill transient guard active"
    else:
        diag = "normal: within healthy envelope"
    diag = diag + f" (dt={dt:.2f}V ds={ds:.2f}V err={err_block:.3f}m)"

    return {
        "diagnosis": diag,
        "adjusted_setpoints": out_setpoints,
        "anomaly_flags": {"tank1": flag1, "tank2": flag2},
    }
