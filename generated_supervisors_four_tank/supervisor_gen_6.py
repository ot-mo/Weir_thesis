def supervise(telemetry_window, active_setpoints, nominal_targets):
    # Four-tank plant (Johansson benchmark), gamma = 0.2 -> cross-dominant,
    # non-minimum-phase regime.  A tank leak is fully rejected in the level
    # channel (episode IAE is fault-invariant), so the only observable is the
    # steady-state actuator imbalance.  Solving the two steady-state mass
    # balances for this geometry gives the healthy specific-effort ratio
    #     R0 = ((1-g)*u2/u1 - g) / ((1-g)*u1/u2 - g),   u_i = sqrt(h_i)
    # and R = (v1/u1)/(v2/u2).  A tank-1 leak lowers R below R0, a tank-2 leak
    # raises it; the reference is external to the telemetry window, so it is
    # valid from the very first sample of a fault present from t=0.
    GAMMA = 0.2
    DEV_TOL = 0.15      # whole-window ratio deviation that counts as a fault
    RECENT_TOL = 0.05   # weaker persistence check on the recent half
    MIN_N = 3

    def med(vals):
        sv = sorted(vals)
        m = len(sv)
        if m == 0:
            return 0.0
        if m % 2 == 1:
            return sv[m // 2]
        return 0.5 * (sv[m // 2 - 1] + sv[m // 2])

    def twin_dev(steps):
        if not steps:
            return None
        h1 = med([s["tank1"]["level"] for s in steps])
        h2 = med([s["tank2"]["level"] for s in steps])
        v1 = med([s["tank1"]["pump_effort"] for s in steps])
        v2 = med([s["tank2"]["pump_effort"] for s in steps])
        if h1 <= 0.0 or h2 <= 0.0 or v1 <= 0.0 or v2 <= 0.0:
            return None
        u1 = h1 ** 0.5
        u2 = h2 ** 0.5
        r = u2 / u1
        num = (1.0 - GAMMA) * r - GAMMA
        den = (1.0 - GAMMA) / r - GAMMA
        if num <= 1e-3 or den <= 1e-3:
            return None
        ref = num / den
        ratio = (v1 / u1) / (v2 / u2)
        return ratio / ref

    flag1 = False
    flag2 = False
    n = len(telemetry_window)

    if n >= MIN_N:
        dev_all = twin_dev(telemetry_window)
        half = max(3, n // 2)
        dev_recent = twin_dev(telemetry_window[-half:])
        if dev_all is not None and dev_recent is not None:
            if dev_all < 1.0 - DEV_TOL and dev_recent < 1.0 - RECENT_TOL:
                flag1 = True
            elif dev_all > 1.0 + DEV_TOL and dev_recent > 1.0 + RECENT_TOL:
                flag2 = True

    nom1 = float(nominal_targets["tank1"])
    nom2 = float(nominal_targets["tank2"])
    sp1 = float(active_setpoints["tank1"])
    sp2 = float(active_setpoints["tank2"])

    # Supervisory regulation: small bounded demand reduction while a fault is
    # active, monotone restore towards nominal once that tank's flag clears.
    LOWER_STEP = 0.003
    RESTORE_STEP = 0.004
    MAX_DROP = 0.015

    def adjust(sp, nom, flagged):
        if flagged:
            floor = nom - MAX_DROP
            if sp > floor:
                return max(floor, sp - LOWER_STEP)
            return sp
        if sp < nom:
            return min(nom, sp + RESTORE_STEP)
        if sp > nom:
            return max(nom, sp - RESTORE_STEP)
        return sp

    new_sp1 = adjust(sp1, nom1, flag1)
    new_sp2 = adjust(sp2, nom2, flag2)

    if flag1 or flag2:
        bits = []
        if flag1:
            bits.append("tank1 specific-effort ratio LOW (tank1-side fault/leak)")
        if flag2:
            bits.append("tank2 specific-effort ratio HIGH (tank2-side fault/leak)")
        diagnosis = "; ".join(bits)
    else:
        diagnosis = "nominal: twin specific-effort ratio matches plant geometry"

    return {
        "diagnosis": diagnosis,
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": bool(flag1), "tank2": bool(flag2)},
    }
