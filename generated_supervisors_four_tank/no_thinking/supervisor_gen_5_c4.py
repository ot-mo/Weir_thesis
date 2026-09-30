def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    if n == 0:
        return {
            "diagnosis": "empty window",
            "adjusted_setpoints": {"tank1": active_setpoints["tank1"], "tank2": active_setpoints["tank2"]},
            "anomaly_flags": {"tank1": False, "tank2": False},
        }

    last = telemetry_window[-1]

    def series(tank, key):
        return [s[tank][key] for s in telemetry_window]

    eff1 = series("tank1", "pump_effort")
    eff2 = series("tank2", "pump_effort")
    lvl1 = series("tank1", "level")
    lvl2 = series("tank2", "level")

    sp1 = active_setpoints["tank1"]
    sp2 = active_setpoints["tank2"]
    nom1 = nominal_targets["tank1"]
    nom2 = nominal_targets["tank2"]

    WIN = 10
    def mean_tail(xs, k):
        m = xs[-k:] if len(xs) >= k else xs
        return sum(m) / float(len(m))

    e1 = mean_tail(eff1, WIN)
    e2 = mean_tail(eff2, WIN)

    # Steady-state feedforward effort model at the current setpoints.
    # Healthy closed loop at nominal (0.30, 0.35): tank1 loop (pump2) ~9.35 V,
    # tank2 loop (pump1) ~8.96 V. Sensitivity to own setpoint ~ +6.7 V per m
    # (from the operating point) plus weak cross term.
    base1 = 9.35 + 6.7 * (sp1 - 0.30) + 1.0 * (sp2 - 0.35)
    base2 = 8.96 + 4.5 * (sp2 - 0.35) + 0.8 * (sp1 - 0.30)
    if base1 < 6.0:
        base1 = 6.0
    if base2 < 6.0:
        base2 = 6.0

    need1 = base1
    need2 = base2

    exc1 = e1 - need1
    exc2 = e2 - need2

    sl1 = (lvl1[-1] - lvl1[0]) / float(len(lvl1) - 1) if len(lvl1) > 1 else 0.0
    sl2 = (lvl2[-1] - lvl2[0]) / float(len(lvl2) - 1) if len(lvl2) > 1 else 0.0

    err1 = sp1 - lvl1[-1]
    err2 = sp2 - lvl2[-1]

    EXC_ENTER = 0.90
    EXC_EXIT = 0.45
    EXC_ENTER2 = 0.70
    EXC_EXIT2 = 0.35
    CONV_EPS = 0.0035
    DEFICIT = 0.018

    def not_converging(slope, err):
        return (abs(slope) < CONV_EPS and err > DEFICIT) or (slope < -CONV_EPS)

    nc1 = not_converging(sl1, err1)
    nc2 = not_converging(sl2, err2)

    def tail_streak(xs, cond, need):
        c = 0
        for v in reversed(xs):
            if cond(v):
                c += 1
            else:
                break
        return c

    enter1 = (exc1 > EXC_ENTER) and nc1
    enter2 = (exc2 > EXC_ENTER2) and nc2

    clear1 = (exc1 < EXC_EXIT) or (abs(sl1) > 2.0 * CONV_EPS and err1 < DEFICIT)
    clear2 = (exc2 < EXC_EXIT2) or (abs(sl2) > 2.0 * CONV_EPS and err2 < DEFICIT)

    # Hysteresis: if already trimming (sp below nominal), require a real clear.
    if sp1 < nom1 - 1e-9:
        tank1_anom = not clear1
    else:
        tank1_anom = bool(enter1)

    if sp2 < nom2 - 1e-9:
        tank2_anom = not clear2
    else:
        tank2_anom = bool(enter2)

    # Never flag during an uninterrupted fast convergence (healthy start-up).
    improving1 = sl1 > 2.0 * CONV_EPS and err1 < 0.05
    improving2 = sl2 > 2.0 * CONV_EPS and err2 < 0.05
    if improving1 and exc1 < EXC_ENTER:
        tank1_anom = False
    if improving2 and exc2 < EXC_ENTER2:
        tank2_anom = False

    LOWER_STEP = 0.012
    RESTORE_STEP = 0.008
    MIN_SP = 0.05

    if tank1_anom:
        new_sp1 = max(MIN_SP, sp1 - LOWER_STEP) if sp1 > MIN_SP else sp1
    elif sp1 < nom1:
        new_sp1 = min(nom1, sp1 + RESTORE_STEP)
    else:
        new_sp1 = sp1

    if tank2_anom:
        new_sp2 = max(MIN_SP, sp2 - LOWER_STEP) if sp2 > MIN_SP else sp2
    elif sp2 < nom2:
        new_sp2 = min(nom2, sp2 + RESTORE_STEP)
    else:
        new_sp2 = sp2

    return {
        "diagnosis": "t1 a=%s exc=%.2f need=%.2f lvl=%.3f sl=%.4f; t2 a=%s exc=%.2f need=%.2f lvl=%.3f sl=%.4f" % (
            tank1_anom, exc1, need1, lvl1[-1], sl1, tank2_anom, exc2, need2, lvl2[-1], sl2),
        "adjusted_setpoints": {"tank1": float(new_sp1), "tank2": float(new_sp2)},
        "anomaly_flags": {"tank1": bool(tank1_anom), "tank2": bool(tank2_anom)},
    }
