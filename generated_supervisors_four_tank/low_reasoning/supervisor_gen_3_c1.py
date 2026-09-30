def supervise(telemetry_window, active_setpoints, nominal_targets):
    SLOPE_DROP = -0.0015
    SLOPE_FLAT = 0.0005
    SLOPE_RISE = 0.0008
    ERR_DROP = 0.04
    ERR_SAT = 0.05
    MARGIN = 0.02
    EFF_HI = {'tank1': 11.0, 'tank2': 9.7}
    SET_ERR = 0.06
    LO, HI = 0.05, 0.48

    flags = {}
    sps = {}
    for tank in ('tank1', 'tank2'):
        nom = float(nominal_targets[tank])
        levels = [float(s[tank]['level']) for s in telemetry_window]
        efforts = [float(s[tank]['pump_effort']) for s in telemetry_window]
        n = len(levels)
        if n < 5:
            flags[tank] = False
            sps[tank] = nom
            continue
        L = levels[-1]
        k = min(10, n)
        slope = (levels[-1] - levels[-k]) / float(k - 1)
        e_max = max(efforts[-10:]) if n >= 10 else max(efforts)
        err_nom = nom - L
        drop = (slope < SLOPE_DROP) and (err_nom > ERR_DROP) and (L < nom - MARGIN)
        sat = (e_max >= EFF_HI[tank]) and (slope < SLOPE_FLAT) and (err_nom > ERR_SAT) and (L < nom - MARGIN)
        flag = bool(drop or sat)
        if slope > SLOPE_RISE:
            flag = False
        flags[tank] = flag
        if flag and e_max >= EFF_HI[tank] and err_nom > SET_ERR:
            target = L + SET_ERR
            if target > nom:
                target = nom
            if target < LO:
                target = LO
            if target > HI:
                target = HI
            sps[tank] = round(target, 4)
        else:
            sps[tank] = nom
    diag = ('tank1 flag=' + str(flags['tank1']) + ' sp=' + str(sps['tank1']) +
            '; tank2 flag=' + str(flags['tank2']) + ' sp=' + str(sps['tank2']))
    return {
        'diagnosis': diag,
        'adjusted_setpoints': sps,
        'anomaly_flags': flags,
    }
