def supervise(telemetry_window, active_setpoints, nominal_targets):
    eff1 = [step["tank1"]["pump_effort"] for step in telemetry_window]
    eff2 = [step["tank2"]["pump_effort"] for step in telemetry_window]
    err1 = [step["tank1"]["error"] for step in telemetry_window]
    err2 = [step["tank2"]["error"] for step in telemetry_window]

    def analyze(eff, err, ceil):
        n = len(eff)
        m = 10 if n >= 10 else n
        rmax = eff[n - m]
        i = n - m
        while i < n:
            if eff[i] > rmax:
                rmax = eff[i]
            i += 1
        half = n // 2
        if half < 1:
            half = 1
        early = sum(abs(e) for e in err[:half]) / half
        recent = sum(abs(e) for e in err[half:]) / (n - half)
        # A fault drives the loop toward its 12 V limit, so an absolute effort
        # ceiling is the robust fingerprint: healthy effort never exceeds
        # ~10.6 V (tank1) or ~9.3 V (tank2) even during start-up.
        # When the fault clears the loop may stay saturated while the level
        # recovers, so a rapidly shrinking error (recovery) clears the flag.
        decreasing = (early - recent) > 0.03
        anomaly = (rmax >= ceil) and (recent > 0.04) and (not decreasing)
        return anomaly

    a1 = analyze(eff1, err1, 10.75)
    a2 = analyze(eff2, err2, 10.0)

    def clamp(v):
        if v < 0.05:
            return 0.05
        if v > 0.48:
            return 0.48
        return v

    def restore(sp, nom):
        if sp < nom:
            v = sp + 0.03
            if v > nom:
                v = nom
            return clamp(v)
        if sp > nom:
            v = sp - 0.03
            if v < nom:
                v = nom
            return clamp(v)
        return clamp(sp)

    new1 = restore(active_setpoints["tank1"], nominal_targets["tank1"])
    new2 = restore(active_setpoints["tank2"], nominal_targets["tank2"])

    diag = "tank1 anomaly=%s (max_effort=%.2f); tank2 anomaly=%s (max_effort=%.2f)" % (
        a1, max(eff1), a2, max(eff2))

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": new1, "tank2": new2},
        "anomaly_flags": {"tank1": a1, "tank2": a2},
    }
