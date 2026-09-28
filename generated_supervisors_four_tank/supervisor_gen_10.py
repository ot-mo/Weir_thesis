def supervise(telemetry_window, active_setpoints, nominal_targets):
    # External anchors measured on a healthy, fault-free episode of THIS plant
    # (plain PID, no supervisor), never re-derived from the window:
    #   v1 mean 10.41 (std 2.27, range 1.92-12.00)
    #   v2 mean  7.36 (std 3.16, range 2.58-12.00)
    #   total v1+v2 = 17.77 V, split v1-v2 = 3.05 V
    #   mean|error| = 0.0740 (tank1) / 0.0832 (tank2), single-sample max 0.19
    TOTAL_NOM = 17.77
    SPLIT_NOM = 3.05
    ERR_GUARD = 0.115
    W = 40

    sp1 = active_setpoints['tank1']
    sp2 = active_setpoints['tank2']
    nom1 = nominal_targets['tank1']
    nom2 = nominal_targets['tank2']

    flag1 = False
    flag2 = False
    note = 'no effort/head imbalance'

    n = len(telemetry_window)

    if n >= 15:
        if n > W:
            tail = telemetry_window[-W:]
        else:
            tail = telemetry_window
        m = len(tail)

        sv1 = 0.0
        sv2 = 0.0
        serr = 0.0
        for step in tail:
            sv1 = sv1 + step['tank1']['pump_effort']
            sv2 = sv2 + step['tank2']['pump_effort']
            serr = serr + abs(step['tank1']['error']) + abs(step['tank2']['error'])
        mv1 = sv1 / m
        mv2 = sv2 / m
        mean_err = serr / (2.0 * m)
        mean_tot = mv1 + mv2
        mean_split = mv1 - mv2
        dev_tot = mean_tot - TOTAL_NOM
        dev_split = mean_split - SPLIT_NOM

        vt = 0.0
        vs = 0.0
        for step in tail:
            tt = step['tank1']['pump_effort'] + step['tank2']['pump_effort']
            dd = step['tank1']['pump_effort'] - step['tank2']['pump_effort']
            vt = vt + (tt - mean_tot) * (tt - mean_tot)
            vs = vs + (dd - mean_split) * (dd - mean_split)
        vt = vt / m
        vs = vs / m
        if vt < 0.0:
            vt = 0.0
        if vs < 0.0:
            vs = 0.0
        se_tot = 3.0 * (vt ** 0.5) / (m ** 0.5)
        se_split = 3.0 * (vs ** 0.5) / (m ** 0.5)

        th_tot = 2.0
        if th_tot < se_tot:
            th_tot = se_tot
        th_split = 3.0
        if th_split < se_split:
            th_split = se_split

        if mean_err <= ERR_GUARD:
            if dev_tot > th_tot:
                if dev_split < -th_split:
                    flag1 = True
                    note = 'tank1 total-effort excess with cross-split drop'
                elif dev_split > th_split:
                    flag2 = True
                    note = 'tank2 total-effort excess with cross-split rise'
                else:
                    sym_th = 4.5
                    if sym_th < 4.0 * se_tot:
                        sym_th = 4.0 * se_tot
                    if dev_tot > sym_th and abs(dev_split) < 1.2:
                        prev_ok = True
                        if n >= 2 * W:
                            prev = telemetry_window[n - 2 * W:n - W]
                            if len(prev) >= 8:
                                ps = 0.0
                                for step in prev:
                                    ps = ps + step['tank1']['pump_effort'] + step['tank2']['pump_effort']
                                if (ps / len(prev)) - TOTAL_NOM <= sym_th:
                                    prev_ok = False
                        if prev_ok:
                            flag1 = True
                            flag2 = True
                            note = 'symmetric effort excess on both branches'

    if not flag1 and sp1 < nom1:
        sp1 = min(nom1, sp1 + 0.01)
    if not flag2 and sp2 < nom2:
        sp2 = min(nom2, sp2 + 0.01)

    if flag1 and flag2:
        diag = 'both branches anomalous (' + note + ')'
    elif flag1:
        diag = 'tank1 anomalous (' + note + ')'
    elif flag2:
        diag = 'tank2 anomalous (' + note + ')'
    else:
        diag = 'nominal operation; no effort/head imbalance outside the healthy envelope'

    return {
        'diagnosis': diag,
        'adjusted_setpoints': {'tank1': sp1, 'tank2': sp2},
        'anomaly_flags': {'tank1': flag1, 'tank2': flag2},
    }
