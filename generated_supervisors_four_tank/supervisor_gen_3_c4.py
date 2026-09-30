def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    if n < 20:
        return {
            "diagnosis": "insufficient telemetry",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    # Per-tank effort rails, sized from the loop's OWN fault-free envelope.
    # Healthy maxima: tank1 loop 10.59 V (start-up) / 10.54 V (settled);
    #                 tank2 loop  8.76 V (start-up) /  9.26 V (settled).
    # A leak drives the leaking tank's own off-diagonal loop to the 12 V pump
    # ceiling; the partner loop only shifts ~0.5-1.0 V when the OTHER leak
    # clears, so every rail keeps >= 0.45 V (tank1) / >= 1.0 V (tank2) of
    # head-room above the corresponding healthy maximum.
    RAIL_HIGH = {"tank1": 11.40, "tank2": 10.90}
    RAIL_LOW = {"tank1": 11.05, "tank2": 10.35}
    N_HARD = 1        # samples over RAIL_HIGH inside the newest 6
    N_SOFT = 3        # samples over RAIL_LOW inside the newest 6
    RECENT = 6        # newest samples used for onset (10 s call cadence,
                      # so the newest samples date the onset most tightly)
    SOFT_ERR = 0.03   # companion error test for the soft tier only

    # Level-rate discriminator (m/s). Leak-limited creep is <= 0.0013 m/s;
    # post-clear refill of a wound-up loop is 0.0025-0.0043 m/s.
    RATE_SPAN = 3
    RATE_REFILL = 0.0016

    SP_STEP = 0.02
    SP_DROP = 0.04
    SP_MIN = 0.05
    SP_MAX = 0.48

    def detect(tank):
        eff = [s[tank]["pump_effort"] for s in telemetry_window]
        lvl = [s[tank]["level"] for s in telemetry_window]
        err = [s[tank]["error"] for s in telemetry_window]

        recent = eff[-RECENT:]
        hard = 0
        soft = 0
        for v in recent:
            if v >= RAIL_HIGH[tank]:
                hard += 1
            if v >= RAIL_LOW[tank]:
                soft += 1

        span = RATE_SPAN
        if span > n - 1:
            span = n - 1
        acc = 0.0
        for i in range(n - span, n):
            acc += lvl[i] - lvl[i - 1]
        rate = acc / float(span)

        refilling = rate > RATE_REFILL
        high = (hard >= N_HARD) or (soft >= N_SOFT and err[-1] >= SOFT_ERR)
        anomaly = bool(high and not refilling)
        return anomaly, hard, soft, rate

    a1, h1c, s1c, r1 = detect("tank1")
    a2, h2c, s2c, r2 = detect("tank2")

    def next_sp(sp, nom, anomaly, err):
        lo = nom - SP_DROP
        if lo < SP_MIN:
            lo = SP_MIN
        if anomaly:
            new = sp - SP_STEP
            if new < lo:
                new = lo
        else:
            if err <= 0.015:
                new = nom
            else:
                new = sp + SP_STEP
                if new > nom:
                    new = nom
        if new < SP_MIN:
            new = SP_MIN
        if new > SP_MAX:
            new = SP_MAX
        return round(new, 4)

    e1 = telemetry_window[-1]["tank1"]["error"]
    e2 = telemetry_window[-1]["tank2"]["error"]
    sp1n = next_sp(sp1, nom1, a1, e1)
    sp2n = next_sp(sp2, nom2, a2, e2)

    diag = ("t1 flag={} hard={} soft={} rate={:+.4f} | "
            "t2 flag={} hard={} soft={} rate={:+.4f}").format(
                a1, h1c, s1c, r1, a2, h2c, s2c, r2)

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": sp1n, "tank2": sp2n},
        "anomaly_flags": {"tank1": a1, "tank2": a2},
    }
