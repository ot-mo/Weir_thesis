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

    # --- thresholds ------------------------------------------------------
    # A leak in a lower tank is always compensated by that tank's OWN
    # off-diagonal loop (tank1 leak -> pump2 = tank1.pump_effort, tank2 leak
    # -> pump1 = tank2.pump_effort) and that loop saturates against the 12 V
    # ceiling (a 1.5x leak already needs ~15 V).  Fault-free loop-effort
    # maxima: tank1 loop 10.59 V (start-up) / 10.54 V (settled); tank2 loop
    # 8.76 V / 9.26 V.  11.4 V keeps >= 0.8 V above the tank1 loop envelope,
    # so a SINGLE sample there is already decisive -> no need for 2 samples
    # (which cost a whole call of onset latency).
    RAIL_V = 11.4
    LOOK = 10          # one-second samples inspected (10 s since last call)
    RISE_SPAN = 3      # one-second level differences used for the trend
    # Leak creep reaches <= 0.0013 m/s; post-clear refilling is 0.0025-0.0043
    # m/s.  0.0018 m/s sits between them (the old 0.0012 sat BELOW creep and
    # suppressed genuine slow onsets).
    RISE_FAST = 0.0018
    # Auxiliary (faster) path: per-loop effort levels above anything healthy
    # operation can produce (tank1 loop max 10.59 V, tank2 loop max 9.26 V),
    # plus a large level deficit and a non-positive level rate.
    AUX_V = {"tank1": 11.0, "tank2": 9.9}
    AUX_RISE = 0.7     # loop must have climbed this much inside the window
    AUX_ERR = 0.05     # level deficit, only used together with effort AUX_V
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

        win = eff[-LOOK:]
        max_eff = max(win)
        min_eff = min(win)

        span = RISE_SPAN
        if span > n - 1:
            span = n - 1
        rate = (lvl[n - 1] - lvl[n - 1 - span]) / float(span)
        refilling = rate > RISE_FAST

        # Stage 1: loop pinned on the pump rail right now (one sample is
        # enough; healthy loops never come near 11.4 V).
        on_rail = max_eff >= RAIL_V

        # Stage 2: auxiliary - the loop is already well above any healthy
        # value, has climbed inside the window, the level is well below its
        # setpoint and is not rising.  This fires one call before the rail.
        aux = (max_eff >= AUX_V[tank] and
               (max_eff - min_eff) >= AUX_RISE and
               err[-1] >= AUX_ERR and
               rate <= 0.0)

        anomaly = bool((on_rail or aux) and not refilling)
        return anomaly, max_eff, rate

    a1, m1, r1 = detect("tank1")
    a2, m2, r2 = detect("tank2")

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

    diag = ("tank1: flag={} maxV={:.2f} dLdt={:+.4f}m/s | "
            "tank2: flag={} maxV={:.2f} dLdt={:+.4f}m/s").format(
        a1, m1, r1, a2, m2, r2)

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": sp1n, "tank2": sp2n},
        "anomaly_flags": {"tank1": a1, "tank2": a2},
    }
