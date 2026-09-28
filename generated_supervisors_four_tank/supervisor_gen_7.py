def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ------------------------------------------------------------------
    # Four-tank structure (gamma1 = gamma2 = 0.2, non-minimum-phase tune):
    #   pump1 -> tank1 (weight 0.2)  and -> tank4 -> tank2 (weight 0.8)
    #   pump2 -> tank2 (weight 0.2)  and -> tank3 -> tank1 (weight 0.8)
    #
    # Steady-state mass balances of the two MEASURED tanks, with one common
    # plant gain g (effort -> metres^(3/2)):
    #   DIRECT*v1 + CROSS*v2 = g*sqrt(h1)
    #   CROSS*v1 + DIRECT*v2 = g*sqrt(h2)
    # Eliminating g gives a scale-free reference for the cross-branch
    # specific-effort ratio (effort per unit sqrt(head)):
    #   R_model(u1,u2) = (CROSS*u2/u1 - DIRECT) / (CROSS*u1/u2 - DIRECT)
    # The measured R = (v1/u1)/(v2/u2) equals R_model exactly in the healthy
    # steady state, for ANY pair of heads or setpoints, so dev = R/R_model
    # is 1 in health and needs no window baseline (a fault already active in
    # the very first sample of the window is still visible).
    #
    # Being cross-dominant, a leak makes the leaking branch's OWN pump
    # throttle back while the cross-coupled pump takes up the load:
    #   tank1 leak -> dev FALLS below 1
    #   tank2 leak -> dev RISES above 1
    # The two branches therefore always move in opposite directions, so one
    # scalar can never false-positive the healthy twin of a single leak.
    # ------------------------------------------------------------------
    DIRECT = 0.2
    CROSS = 0.8

    try:
        sp1 = float(active_setpoints["tank1"])
    except Exception:
        sp1 = 0.0
    try:
        sp2 = float(active_setpoints["tank2"])
    except Exception:
        sp2 = 0.0
    try:
        nom1 = float(nominal_targets["tank1"])
    except Exception:
        nom1 = sp1
    try:
        nom2 = float(nominal_targets["tank2"])
    except Exception:
        nom2 = sp2

    devs = []
    try:
        for step in telemetry_window:
            t1 = step["tank1"]
            t2 = step["tank2"]
            h1 = float(t1["level"])
            h2 = float(t2["level"])
            v1 = float(t1["pump_effort"])
            v2 = float(t2["pump_effort"])
            if h1 <= 0.0 or h2 <= 0.0 or v2 <= 0.0 or v1 < 0.0:
                continue
            u1 = h1 ** 0.5
            u2 = h2 ** 0.5
            num = CROSS * u2 / u1 - DIRECT
            den = CROSS * u1 / u2 - DIRECT
            if num <= 1e-9 or den <= 1e-9:
                continue
            r_model = num / den
            r_meas = (v1 / u1) / (v2 / u2)
            devs.append(r_meas / r_model)
    except Exception:
        devs = []

    def median(vals):
        sv = sorted(vals)
        m = len(sv)
        if m == 0:
            return 1.0
        if m % 2 == 1:
            return sv[m // 2]
        return 0.5 * (sv[m // 2 - 1] + sv[m // 2])

    # Symmetric, multiplicative gate: how far the cross-branch imbalance must
    # sit from the geometric healthy reference before a leak is declared.
    # Normal limit-cycle swing of this cross-coupled loop is only a few per
    # cent of the ratio, while a real leak moves the two pumps in opposite
    # directions and shifts dev by tens of per cent, so there is a wide gap.
    LOW = 0.88
    HIGH = 1.0 / LOW

    tank1_anomaly = False
    tank2_anomaly = False
    med_tail = 1.0

    if len(devs) >= 6:
        k = len(devs) // 2
        if k < 3:
            k = 3
        tail = devs[-k:]
        med_tail = median(tail)
        m = len(tail)
        below = 0
        above = 0
        for d in tail:
            if d < LOW:
                below += 1
            elif d > HIGH:
                above += 1
        if med_tail < LOW and below >= 0.7 * m:
            tank1_anomaly = True
        elif med_tail > HIGH and above >= 0.7 * m:
            tank2_anomaly = True

    # --- supervisory set-point policy ---------------------------------
    # Bounded demand relief (< 8% of nominal) on the flagged branch only, so
    # the supervisor's own reduction can never be re-read as a level deficit
    # and re-trigger itself; restoration is a single step back to nominal as
    # soon as the imbalance has genuinely gone, so no residual gap is left.
    LOWER_STEP = 0.01
    MAX_DROP = 0.02
    RESTORE_STEP = 0.02

    def adjust(sp, nom, anomaly):
        if anomaly:
            floor = nom - MAX_DROP
            if floor < 0.05:
                floor = 0.05
            target = sp - LOWER_STEP
            if target > nom:
                target = nom
            if target < floor:
                target = floor
            return target
        if sp < nom:
            target = sp + RESTORE_STEP
            if target > nom:
                target = nom
            return target
        return sp

    new_sp1 = adjust(sp1, nom1, tank1_anomaly)
    new_sp2 = adjust(sp2, nom2, tank2_anomaly)

    if tank1_anomaly or tank2_anomaly:
        parts = []
        if tank1_anomaly:
            parts.append("tank1 leak-like")
        if tank2_anomaly:
            parts.append("tank2 leak-like")
        diagnosis = ("cross-branch effort/head imbalance (dev="
                     + str(round(med_tail, 3)) + "): " + "; ".join(parts))
    else:
        diagnosis = ("cross-branch effort/head balance consistent with plant geometry "
                     "(dev=" + str(round(med_tail, 3)) + "); no anomaly")

    return {
        "diagnosis": diagnosis,
        "adjusted_setpoints": {"tank1": float(new_sp1), "tank2": float(new_sp2)},
        "anomaly_flags": {"tank1": bool(tank1_anomaly), "tank2": bool(tank2_anomaly)},
    }