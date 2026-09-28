def supervise(telemetry_window, active_setpoints, nominal_targets):
    def get(d, k, default):
        try:
            return float(d[k])
        except (KeyError, TypeError, ValueError):
            return float(default)

    nom1 = get(nominal_targets, "tank1", 0.3)
    nom2 = get(nominal_targets, "tank2", 0.3)
    sp1 = get(active_setpoints, "tank1", nom1)
    sp2 = get(active_setpoints, "tank2", nom2)

    steps = telemetry_window if isinstance(telemetry_window, list) else []
    n = len(steps)

    if n < 4:
        return {
            "diagnosis": "insufficient telemetry; holding setpoints",
            "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    def col(tank, key):
        out = []
        for s in steps:
            try:
                out.append(float(s[tank][key]))
            except (KeyError, TypeError, ValueError):
                out.append(0.0)
        return out

    l1 = col("tank1", "level")
    e1 = col("tank1", "pump_effort")
    r1 = col("tank1", "error")
    l2 = col("tank2", "level")
    e2 = col("tank2", "pump_effort")
    r2 = col("tank2", "error")

    def mean(v):
        return sum(v) / len(v) if v else 0.0

    w = max(2, n // 4)

    def feats(levels, efforts, errors, nom):
        early_eff = mean(efforts[:w])
        recent_eff = mean(efforts[-w:])
        early_lvl = mean(levels[:w])
        recent_lvl = mean(levels[-w:])
        recent_err = errors[-w:]

        eff_ratio = recent_eff / early_eff if early_eff > 1e-6 else 1.0

        a = sum(abs(x) for x in recent_err)
        bias = abs(sum(recent_err)) / a if a > 1e-9 else 0.0

        scale = abs(nom) if abs(nom) > 1e-6 else 1.0
        deficit = (nom - recent_lvl) / scale

        he = early_lvl if early_lvl > 1e-6 else 1e-6
        hr = recent_lvl if recent_lvl > 1e-6 else 1e-6
        spec_e = early_eff / (he ** 0.5)
        spec_r = recent_eff / (hr ** 0.5)

        return {
            "eff_ratio": eff_ratio,
            "bias": bias,
            "deficit": deficit,
            "spec_e": spec_e,
            "spec_r": spec_r,
        }

    f1 = feats(l1, e1, r1, nom1)
    f2 = feats(l2, e2, r2, nom2)

    def rel_cross(fi, fj):
        if (fi["spec_e"] > 1e-6 and fi["spec_r"] > 1e-6 and
                fj["spec_e"] > 1e-6 and fj["spec_r"] > 1e-6):
            base = fi["spec_e"] / fj["spec_e"]
            now = fi["spec_r"] / fj["spec_r"]
            if base > 1e-6:
                return now / base
        return 1.0

    c1 = rel_cross(f1, f2)
    c2 = rel_cross(f2, f1)

    EFF_RATIO_TH = 1.25
    CROSS_TH = 1.45
    DEFICIT_TH = 0.11
    BIAS_TH = 0.45

    def detect(f, c):
        effort_evidence = (f["eff_ratio"] > EFF_RATIO_TH) or (c > CROSS_TH)
        error_evidence = (f["deficit"] > DEFICIT_TH) or (f["bias"] > BIAS_TH)
        strong = (f["eff_ratio"] > 2.0) or (c > 2.2)
        return (effort_evidence and error_evidence) or strong

    anom1 = detect(f1, c1)
    anom2 = detect(f2, c2)

    LOWER_STEP = 0.015
    RESTORE_STEP = 0.03

    def adjust(sp, nom, anom):
        floor = max(0.05, nom - 0.025)
        if anom:
            return max(floor, sp - LOWER_STEP)
        if sp < nom:
            nxt = sp + RESTORE_STEP
            if nom - nxt < 0.005:
                nxt = nom
            return min(nom, nxt)
        if sp > nom:
            nxt = sp - RESTORE_STEP
            if nxt - nom < 0.005:
                nxt = nom
            return max(nom, nxt)
        return nom

    new1 = adjust(sp1, nom1, anom1)
    new2 = adjust(sp2, nom2, anom2)

    diag = ("tank1 %s (eff_ratio=%.2f cross=%.2f bias=%.2f deficit=%.2f) | "
            "tank2 %s (eff_ratio=%.2f cross=%.2f bias=%.2f deficit=%.2f)") % (
        "ANOMALY" if anom1 else "normal", f1["eff_ratio"], c1, f1["bias"], f1["deficit"],
        "ANOMALY" if anom2 else "normal", f2["eff_ratio"], c2, f2["bias"], f2["deficit"])

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": float(new1), "tank2": float(new2)},
        "anomaly_flags": {"tank1": bool(anom1), "tank2": bool(anom2)},
    }
