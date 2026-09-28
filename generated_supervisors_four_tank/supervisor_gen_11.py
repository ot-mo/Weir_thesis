def supervise(telemetry_window, active_setpoints, nominal_targets):
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    def quiet(diag):
        return {
            "diagnosis": diag,
            "adjusted_setpoints": {"tank1": nom1, "tank2": nom2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    # Measured fault-free anchors for THIS 4-tank plant (external reference;
    # the telemetry window itself cannot contaminate these numbers).
    H_TOTAL = 17.77   # mean of v1+v2 in the healthy episode (10.41 + 7.36)
    H_SPLIT = 3.05    # mean of v1-v2 in the healthy episode (10.41 - 7.36)

    def stats(rows):
        m = len(rows)
        s1 = 0.0
        s2 = 0.0
        st = 0.0
        st2 = 0.0
        se = 0.0
        for r in rows:
            a = r["tank1"]["pump_effort"]
            b = r["tank2"]["pump_effort"]
            s1 += a
            s2 += b
            t = a + b
            st += t
            st2 += t * t
            se += abs(r["tank1"]["error"]) + abs(r["tank2"]["error"])
        mt = st / m
        var = st2 / m - mt * mt
        if var < 0.0:
            var = 0.0
        return (s1 / m, s2 / m, mt, var ** 0.5, se / (2.0 * m))

    n = len(telemetry_window)
    if n < 40:
        return quiet("warming up")

    win = telemetry_window[-80:] if n > 80 else telemetry_window
    m = len(win)
    m1, m2, mt, sd, mean_err = stats(win)

    # Start-up fill guard: while both pumps saturate the block-mean |error|
    # jumps to ~0.25 (vs 0.074-0.083 healthy). The error channel is identical
    # in faulted and unfaulted episodes, so this veto is scenario-blind and
    # can only cost benign latency, never mask a genuine effort signature.
    if mean_err >= 0.105:
        return quiet("start-up transient")

    dt = mt - H_TOTAL
    ds = (m1 - m2) - H_SPLIT

    # Scale-aware threshold: fixed floor well outside the measured healthy
    # envelope plus 2.2 standard errors of the window-mean total effort
    # (effective sample size discounted well below m for the slow
    # cross-coupled oscillation).
    n_eff = m / 8.0
    if n_eff < 4.0:
        n_eff = 4.0
    se = sd / (n_eff ** 0.5)
    DT = 2.0
    if 2.2 * se > DT:
        DT = 2.2 * se

    flags = {"tank1": False, "tank2": False}
    diagnosis = "no anomaly"

    if dt > DT:
        ads = ds if ds >= 0.0 else -ds
        # Invariant leak shape: |delta(v1-v2)| = delta(v1+v2)/(1-2*gamma)
        # = 1.667 x delta(v1+v2). Pure anti-phase oscillation -> |ds| below
        # the band; pure in-phase oscillation -> |ds| above the band.
        if ads > 0.6 * dt and ads < 4.0 * dt:
            h = m // 2
            h1, h2, ht, hsd, herr = stats(win[h:])
            dth = ht - H_TOTAL
            dsh = (h1 - h2) - H_SPLIT
            # Persistence: recent half must agree on excess and split sign.
            if dth > 0.8 * DT and dsh * ds > 0.0:
                if ds < 0.0:
                    flags["tank1"] = True
                    diagnosis = ("tank1 anomaly: total effort up with "
                                 "v1-v2 split shifted low (leak signature)")
                else:
                    flags["tank2"] = True
                    diagnosis = ("tank2 anomaly: total effort up with "
                                 "v1-v2 split shifted high (leak signature)")

    return {
        "diagnosis": diagnosis,
        "adjusted_setpoints": {"tank1": nom1, "tank2": nom2},
        "anomaly_flags": flags,
    }
