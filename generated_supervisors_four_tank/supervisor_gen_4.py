def supervise(telemetry_window, active_setpoints, nominal_targets):
    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])
    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])

    def median(vals):
        sv = sorted(vals)
        m = len(sv)
        if m == 0:
            return 0.0
        if m % 2 == 1:
            return sv[m // 2]
        return (sv[m // 2 - 1] + sv[m // 2]) / 2.0

    # Healthy cross-branch specific-effort ratio implied by plant geometry
    # (gamma=0.2, non-minimum-phase). With equal setpoints this is 1.0.
    GAMMA = 0.2
    u1n = max(nom1, 1e-9) ** 0.5
    u2n = max(nom2, 1e-9) ** 0.5
    num = (1.0 - GAMMA) * (u2n / u1n) - GAMMA
    den = (1.0 - GAMMA) * (u1n / u2n) - GAMMA
    sym0 = 1.0
    if abs(den) > 1e-9:
        cand = num / den
        if cand == cand and cand > 1e-6:
            sym0 = cand

    s1s = []
    s2s = []
    ratios = []
    for step in telemetry_window:
        h1 = step["tank1"]["level"]
        h2 = step["tank2"]["level"]
        if h1 > 1e-6 and h2 > 1e-6:
            s1 = step["tank1"]["pump_effort"] / (h1 ** 0.5)
            s2 = step["tank2"]["pump_effort"] / (h2 ** 0.5)
            s1s.append(s1)
            s2s.append(s2)
            if s2 > 1e-9:
                ratios.append(s1 / s2)

    tank1_anom = False
    tank2_anom = False
    note = "insufficient telemetry"

    if len(ratios) >= 6:
        half = max(2, len(ratios) // 2)
        d_all = median(ratios) / sym0
        d_rec = median(ratios[-half:]) / sym0

        # Model-reference detector: a tank-1 leak is compensated mainly by
        # pump 2 (cross path weight 0.8) and pump 1 backs off, so r FALLS;
        # the mirror holds for tank 2. Immune to faults active at window start.
        model1 = (d_rec < 0.90) and (d_all < 0.95)
        model2 = (d_rec > 1.11) and (d_all > 1.05)

        h = max(2, len(s1s) // 2)
        s1_first = median(s1s[:h])
        s1_rec = median(s1s[-h:])
        s2_first = median(s2s[:h])
        s2_rec = median(s2s[-h:])

        recent = telemetry_window[-max(1, len(telemetry_window) // 2):]
        e1 = median([abs(st["tank1"]["error"]) for st in recent])
        e2 = median([abs(st["tank2"]["error"]) for st in recent])
        settled = (e1 < 0.03 * max(nom1, 1e-6)) and (e2 < 0.03 * max(nom2, 1e-6))

        # Model-independent backstop (needs onset inside the window and a
        # settled loop): the two specific efforts must move OPPOSITELY.
        time1 = settled and (s1_first > 1e-9) and (s2_first > 1e-9) and (s1_rec < 0.88 * s1_first) and (s2_rec > 1.14 * s2_first)
        time2 = settled and (s1_first > 1e-9) and (s2_first > 1e-9) and (s2_rec < 0.88 * s2_first) and (s1_rec > 1.14 * s1_first)

        tank1_anom = bool(model1 or time1)
        tank2_anom = bool(model2 or time2)
        note = "ratio=%.3f sym0=%.3f d_all=%.3f d_rec=%.3f" % (median(ratios), sym0, d_all, d_rec)

    STEP = 0.005

    def toward_nominal(sp, nom):
        if sp < nom:
            return min(nom, sp + STEP)
        if sp > nom:
            return max(nom, sp - STEP)
        return sp

    # A flagged tank is held (its own setpoint is never lowered, which would
    # raise v/sqrt(h) and mask its own fault); an unflagged tank is restored.
    new1 = sp1 if tank1_anom else toward_nominal(sp1, nom1)
    new2 = sp2 if tank2_anom else toward_nominal(sp2, nom2)

    return {
        "diagnosis": "tank1_anomaly=%s tank2_anomaly=%s (%s)" % (tank1_anom, tank2_anom, note),
        "adjusted_setpoints": {"tank1": round(new1, 5), "tank2": round(new2, 5)},
        "anomaly_flags": {"tank1": tank1_anom, "tank2": tank2_anom},
    }
