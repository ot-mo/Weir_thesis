def supervise(telemetry_window, active_setpoints, nominal_targets):
    # ---- externally measured fault-free anchors (hard numbers from the
    #      reference episode: v1 mean 10.41, v2 mean 7.36) ----
    TOTAL_ANCHOR = 17.77      # mean(v1 + v2) with no fault
    SPLIT_ANCHOR = 3.05       # mean(v1 - v2) with no fault
    FILL_ERROR_GUARD = 0.115  # (|e1|+|e2|)/2 ~0.25 while filling, 0.078 healthy

    LONG_B = 100              # slow evidence block (~1/6 of a 600-step episode)
    SHORT_B = 50              # free confirmation block (reaches any level first)
    MIN_STEPS = 30
    NEFF = 10.0               # effective independent samples in a 100-step block

    SHAPE_LO = 0.7            # leak shape: |d(split)| / d(total) ~ 1.667
    SHAPE_HI = 2.8
    SYM_SPLIT_TOL = 1.2       # balanced double leak leaves split on its anchor
    DT_FLOOR = 2.5
    DT_SYM_EXTRA = 1.2

    nominal1 = float(nominal_targets.get("tank1", 0.30))
    nominal2 = float(nominal_targets.get("tank2", 0.35))

    n = len(telemetry_window)
    flag1 = False
    flag2 = False
    diagnosis = "no fault signature; setpoints at nominal"

    if n >= MIN_STEPS:
        # scale the threshold with the window's own total-effort spread
        tot_all = []
        for step in telemetry_window:
            tot_all.append(step["tank1"]["pump_effort"] + step["tank2"]["pump_effort"])
        m_all = sum(tot_all) / float(n)
        var_all = 0.0
        for x in tot_all:
            var_all += (x - m_all) * (x - m_all)
        var_all = var_all / float(n)
        sd_tot = var_all ** 0.5

        def block(k):
            k = min(k, n)
            seg = telemetry_window[-k:]
            tot = 0.0
            spl = 0.0
            err = 0.0
            for step in seg:
                e1 = step["tank1"]["pump_effort"]
                e2 = step["tank2"]["pump_effort"]
                tot += e1 + e2
                spl += e1 - e2
                err += abs(step["tank1"]["error"]) + abs(step["tank2"]["error"])
            fk = float(k)
            return tot / fk, spl / fk, err / (2.0 * fk)

        tot_l, spl_l, err_l = block(LONG_B)
        tot_s, spl_s, err_s = block(SHORT_B)

        dt_l = tot_l - TOTAL_ANCHOR
        dt_s = tot_s - TOTAL_ANCHOR
        ds_l = spl_l - SPLIT_ANCHOR
        ds_s = spl_s - SPLIT_ANCHOR

        dt_thr = DT_FLOOR
        scaled = 3.0 * sd_tot / (NEFF ** 0.5)
        if scaled > dt_thr:
            dt_thr = scaled
        dt_sym_thr = dt_thr + DT_SYM_EXTRA

        filling = (err_l > FILL_ERROR_GUARD) or (err_s > FILL_ERROR_GUARD)

        if filling:
            diagnosis = "startup fill transient (block-mean |e| ~0.25): detection suppressed"
        else:
            if dt_l > 0.0:
                r_l = abs(ds_l) / dt_l
            else:
                r_l = 99.0
            if dt_s > 0.0:
                r_s = abs(ds_s) / dt_s
            else:
                r_s = 99.0

            # directional (single-tank) leak: total up, split pushed the other way
            if (dt_l > dt_thr and dt_s > dt_thr and
                    SHAPE_LO <= r_l <= SHAPE_HI and SHAPE_LO <= r_s <= SHAPE_HI):
                if ds_l < 0.0 and ds_s < 0.0:
                    flag1 = True
                    diagnosis = "tank1 leak-shape: total effort above healthy anchor, split displaced negatively"
                elif ds_l > 0.0 and ds_s > 0.0:
                    flag2 = True
                    diagnosis = "tank2 leak-shape: total effort above healthy anchor, split displaced positively"

            # symmetric (balanced double) leak: total up, split sitting on its anchor
            if (dt_l > dt_sym_thr and dt_s > dt_sym_thr and
                    abs(ds_l) < SYM_SPLIT_TOL and abs(ds_s) < SYM_SPLIT_TOL):
                flag1 = True
                flag2 = True
                diagnosis = "symmetric effort excess on both branches, split at healthy level"

    return {
        "diagnosis": diagnosis,
        "adjusted_setpoints": {"tank1": nominal1, "tank2": nominal2},
        "anomaly_flags": {"tank1": flag1, "tank2": flag2},
    }
