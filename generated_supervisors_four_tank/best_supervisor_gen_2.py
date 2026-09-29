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
    # A leaking lower tank is compensated by its OWN off-diagonal loop
    # (tank1 leak -> pump 2 = tank1.pump_effort, tank2 leak -> pump 1 =
    # tank2.pump_effort) which saturates against the 12 V pump ceiling.
    # Fault-free reference maxima: tank1 loop 10.59 V (start-up) /
    # 10.54 V (settled); tank2 loop 8.76 V / 9.26 V.  11.4 V is therefore
    # 0.81 V above anything the healthy tank1 loop and 2.14 V above
    # anything the healthy tank2 loop can produce.
    RAIL_V = 11.4
    RAIL_N = 2        # samples at/above the rail inside the last 10 s
    LOOK = 10         # one-second samples inspected (the 10 s since the
                      # previous call)
    RISE_SPAN = 3     # one-second level differences used for the trend
    RISE_FAST = 0.0012  # m/s: above this the tank is refilling after its
                        # fault cleared (measured 0.0025-0.0043 m/s),
                        # while a compensated leak creeps <=0.0013 m/s
    SP_STEP = 0.02
    SP_DROP = 0.04
    SP_MIN = 0.05
    SP_MAX = 0.48

    def col(tank, field):
        return [step[tank][field] for step in telemetry_window]

    def detect(tank):
        eff = col(tank, "pump_effort")
        lvl = col(tank, "level")

        # Stage 1: is this loop pinned on the pump rail right now?
        cnt = 0
        for v in eff[-LOOK:]:
            if v >= RAIL_V:
                cnt += 1

        # Stage 2: level rate over the last few seconds.
        span = RISE_SPAN
        if span > n - 1:
            span = n - 1
        acc = 0.0
        for i in range(n - span, n):
            acc += lvl[i] - lvl[i - 1]
        rate = acc / float(span)

        on_rail = cnt >= RAIL_N
        refilling = rate > RISE_FAST
        anomaly = bool(on_rail and not refilling)
        return anomaly, cnt, rate

    a1, c1, r1 = detect("tank1")
    a2, c2, r2 = detect("tank2")

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

    diag = ("tank1: flag={} rail={}/10 dLdt={:+.4f}m/s | "
            "tank2: flag={} rail={}/10 dLdt={:+.4f}m/s").format(
        a1, c1, r1, a2, c2, r2)

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": sp1n, "tank2": sp2n},
        "anomaly_flags": {"tank1": a1, "tank2": a2},
    }
