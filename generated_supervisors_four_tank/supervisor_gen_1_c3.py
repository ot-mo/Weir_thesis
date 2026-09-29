def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)

    # tank1.pump_effort is pump 2's voltage (tank1 loop, off-diagonal pairing)
    # tank2.pump_effort is pump 1's voltage (tank2 loop, off-diagonal pairing)
    lvl1 = [step["tank1"]["level"] for step in telemetry_window]
    lvl2 = [step["tank2"]["level"] for step in telemetry_window]
    eff1 = [step["tank1"]["pump_effort"] for step in telemetry_window]
    eff2 = [step["tank2"]["pump_effort"] for step in telemetry_window]

    # Absolute thresholds anchored on fault-free measurements, not on ratios:
    #   fault-free loop effort never exceeds 10.59 V (tank1 loop) or 9.26 V
    #   (tank2 loop); pumps cap at 12 V.  A lower-tank leak forces that tank's
    #   own loop to sit at the cap for as long as the leak lasts.
    SAT = 11.4          # V, ~0.8 V above the highest fault-free effort
    CNT_WIN = 12        # samples inspected
    CNT_NEED = 4        # >=4 s at the cap inside the last 12 s
    SLOPE_WIN = 10      # samples used for the level trend
    RISE_TOL = 0.0018   # m/s; above a leaking tank's flat level, below any refill

    def slope(vals, w):
        m = len(vals)
        if m < 2:
            return 0.0
        if w > m - 1:
            w = m - 1
        if w < 1:
            return 0.0
        return (vals[-1] - vals[-1 - w]) / float(w)

    def anomalous(eff, lvl):
        cw = CNT_WIN if CNT_WIN < n else n
        cnt = 0
        for v in eff[-cw:]:
            if v >= SAT:
                cnt += 1
        if cnt < CNT_NEED:
            return False
        # Loop pinned at the cap.  A leak keeps the level flat or falling;
        # a post-fault refill also pins the loop but the level climbs fast.
        if slope(lvl, SLOPE_WIN) > RISE_TOL:
            return False
        return True

    anom1 = anomalous(eff1, lvl1)
    anom2 = anomalous(eff2, lvl2)

    MIN_SP = 0.05
    MAX_SP = 0.48
    OFFSET = 0.04        # keep the error (and IAE) small without un-pinning the loop
    MAX_RED = 0.12       # bounded reduction, so the pump stays saturated
    RESTORE_STEP = 0.02

    def clamp(v):
        if v < MIN_SP:
            return MIN_SP
        if v > MAX_SP:
            return MAX_SP
        return v

    def next_sp(sp, nom, anom, lvl):
        if anom:
            target = lvl + OFFSET
            floor = nom - MAX_RED
            if target < floor:
                target = floor
            if target < sp:
                sp = target
        elif sp < nom:
            sp = sp + RESTORE_STEP
            if sp > nom:
                sp = nom
        return clamp(sp)

    nsp1 = next_sp(active_setpoints["tank1"], nominal_targets["tank1"], anom1, lvl1[-1])
    nsp2 = next_sp(active_setpoints["tank2"], nominal_targets["tank2"], anom2, lvl2[-1])

    diag = ("tank1(loop->pump2) anomaly={}; tank2(loop->pump1) anomaly={}"
            .format(anom1, anom2))

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": nsp1, "tank2": nsp2},
        "anomaly_flags": {"tank1": anom1, "tank2": anom2},
    }