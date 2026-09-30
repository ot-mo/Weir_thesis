def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    if n < 12:
        return {
            "diagnosis": "insufficient telemetry",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    RAIL_V = 11.4
    RAIL_N = 2
    LOOK = 10
    RISE_SPAN = 3
    RISE_FAST = 0.0020
    RATE_FALL = 0.0015
    ERR_SEC1 = 0.08
    ERR_SEC2 = 0.05
    SP_STEP = 0.02
    SP_DROP = 0.04
    SP_MIN = 0.05
    SP_MAX = 0.48

    def col(tank, field):
        return [step[tank][field] for step in telemetry_window]

    def detect(tank):
        eff = col(tank, "pump_effort")
        lvl = col(tank, "level")
        err = col(tank, "error")

        cnt = 0
        for v in eff[-LOOK:]:
            if v >= RAIL_V:
                cnt += 1

        span = RISE_SPAN
        if span > n - 1:
            span = n - 1
        acc = 0.0
        for i in range(n - span, n):
            acc += lvl[i] - lvl[i - 1]
        rate = acc / float(span)

        refilling = rate > RISE_FAST
        on_rail = cnt >= RAIL_N

        err_last = err[-1]
        if tank == "tank1":
            err_thresh = ERR_SEC1
        else:
            err_thresh = ERR_SEC2
        falling = rate < -RATE_FALL
        secondary = (err_last > err_thresh) and falling

        anomaly = bool((on_rail and not refilling) or secondary)
        return anomaly, cnt, rate, err_last, secondary

    a1, c1, r1, e1, s1 = detect("tank1")
    a2, c2, r2, e2, s2 = detect("tank2")

    def next_sp(sp, nom, anomaly):
        lo = nom - SP_DROP
        if lo < SP_MIN:
            lo = SP_MIN
        if anomaly:
            new = sp - SP_STEP
            if new < lo:
                new = lo
        else:
            new = sp + SP_STEP
            if new > nom:
                new = nom
        if new < SP_MIN:
            new = SP_MIN
        if new > SP_MAX:
            new = SP_MAX
        return round(new, 4)

    sp1n = next_sp(sp1, nom1, a1)
    sp2n = next_sp(sp2, nom2, a2)

    diag = ("tank1: flag={} rail={}/10 dLdt={:+.4f} err={:+.4f} sec={} | "
            "tank2: flag={} rail={}/10 dLdt={:+.4f} err={:+.4f} sec={}").format(
        a1, c1, r1, e1, s1, a2, c2, r2, e2, s2)

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": sp1n, "tank2": sp2n},
        "anomaly_flags": {"tank1": a1, "tank2": a2},
    }
