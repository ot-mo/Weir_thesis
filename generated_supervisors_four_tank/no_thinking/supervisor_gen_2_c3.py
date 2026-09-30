def supervise(telemetry_window, active_setpoints, nominal_targets):
    # Extract telemetry (last 50 one-second samples)
    n = len(telemetry_window)
    t = [s["time"] for s in telemetry_window]
    lvl1 = [s["tank1"]["level"] for s in telemetry_window]
    lvl2 = [s["tank2"]["level"] for s in telemetry_window]
    eff1 = [s["tank1"]["pump_effort"] for s in telemetry_window]
    eff2 = [s["tank2"]["pump_effort"] for s in telemetry_window]
    err1 = [s["tank1"]["error"] for s in telemetry_window]
    err2 = [s["tank2"]["error"] for s in telemetry_window]

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    # Use start of window as the baseline for level drop
    # But because of overlapping windows we need to be careful.
    # We'll use the first 5 samples average vs last 5 samples average
    def mean(vals):
        return sum(vals) / len(vals) if vals else 0.0

    start1 = mean(lvl1[:5])
    start2 = mean(lvl2[:5])
    end1 = mean(lvl1[-5:])
    end2 = mean(lvl2[-5:])

    drop1 = start1 - end1
    drop2 = start2 - end2

    # Recent effort (last 10 samples) for saturation check
    eff1_recent = mean(eff1[-10:])
    eff2_recent = mean(eff2[-10:])

    # Keep a per-call estimate of whether the loop is saturated
    sat1 = eff1_recent > 11.7  # very close to 12
    sat2 = eff2_recent > 11.7

    # Level drop thresholds: healthy settled fluctuations are < 0.01 m
    # during start-up, levels rise, so drops are negative or small.
    drop_thresh = 0.05

    # Also look for sustained drop: levels at start and end of a longer span
    # Use the whole window (50 s) to judge persistence of fall.
    long_drop1 = lvl1[0] - lvl1[-1]
    long_drop2 = lvl2[0] - lvl2[-1]

    # A leak signature: the loop is saturated (or nearly) and level has fallen.
    leak_sig1 = (sat1 and (drop1 > drop_thresh or long_drop1 > drop_thresh))
    leak_sig2 = (sat2 and (drop2 > drop_thresh or long_drop2 > drop_thresh))

    # Additionally consider high effort with persistent error, because a mild
    # leak may not fully saturate but will hold effort above healthy settled.
    eff_thresh1 = 10.5  # healthy settled max ~10.54, but sustained above.
    eff_thresh2 = 9.5   # healthy settled max ~9.26
    err_thresh = 0.08
    err1_recent = mean([abs(e) for e in err1[-10:]])
    err2_recent = mean([abs(e) for e in err2[-10:]])

    # Sustained error plus elevated effort and a level drop (to avoid start-up)
    leak_sig1 = leak_sig1 or (eff1_recent > eff_thresh1 and err1_recent > err_thresh and (drop1 > drop_thresh or long_drop1 > drop_thresh))
    leak_sig2 = leak_sig2 or (eff2_recent > eff_thresh2 and err2_recent > err_thresh and (drop2 > drop_thresh or long_drop2 > drop_thresh))

    # Avoid start-up false positives: if the window is early and levels are still
    # climbing (start level < 0.22 and end level > start level), suppress.
    # We don't know absolute time, but we can look at overall level trend.
    if end1 > start1 and end1 < 0.25:
        leak_sig1 = False
    if end2 > start2 and end2 < 0.25:
        leak_sig2 = False

    # Also require that the level is below its setpoint (positive error)
    # and the effort is above idle to avoid noise flags.
    leak_sig1 = leak_sig1 and (lvl1[-1] < sp1) and (eff1_recent > 9.0)
    leak_sig2 = leak_sig2 and (lvl2[-1] < sp2) and (eff2_recent > 8.0)

    # Setpoint adjustment: lower setpoint if leak detected to avoid pulling
    # the pump into constant saturation and to keep level above safety floor.
    # Lower by 0.02 m but not below 0.10 m to avoid safety violations.
    MIN_SP = 0.10
    LOWER_STEP = 0.02
    RESTORE_STEP = 0.015

    new_sp1 = sp1
    new_sp2 = sp2

    if leak_sig1:
        new_sp1 = max(MIN_SP, sp1 - LOWER_STEP)
        # If we are lowering setpoint, also ensure we don't go below nominal
        # unless necessary; but nominal is 0.3 so fine.
    else:
        # Restore slowly toward nominal if above or below
        if sp1 < nom1:
            new_sp1 = min(nom1, sp1 + RESTORE_STEP)
        elif sp1 > nom1:
            new_sp1 = max(nom1, sp1 - RESTORE_STEP)

    if leak_sig2:
        new_sp2 = max(MIN_SP, sp2 - LOWER_STEP)
    else:
        if sp2 < nom2:
            new_sp2 = min(nom2, sp2 + RESTORE_STEP)
        elif sp2 > nom2:
            new_sp2 = max(nom2, sp2 - RESTORE_STEP)

    # Clamp setpoints to allowed range [0.05, 0.48]
    new_sp1 = max(0.05, min(0.48, new_sp1))
    new_sp2 = max(0.05, min(0.48, new_sp2))

    # Flags are the leak signatures
    flag1 = bool(leak_sig1)
    flag2 = bool(leak_sig2)

    diagnosis = (
        "t1: drop=%.3f eff=%.2f err=%.3f sig=%s | t2: drop=%.3f eff=%.2f err=%.3f sig=%s"
        % (drop1, eff1_recent, err1_recent, flag1, drop2, eff2_recent, err2_recent, flag2)
    )

    return {
        "diagnosis": diagnosis,
        "adjusted_setpoints": {"tank1": new_sp1, "tank2": new_sp2},
        "anomaly_flags": {"tank1": flag1, "tank2": flag2},
    }
