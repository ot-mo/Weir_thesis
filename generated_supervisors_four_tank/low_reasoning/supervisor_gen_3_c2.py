def supervise(telemetry_window, active_setpoints, nominal_targets):
    EFF_HI = {'tank1': 10.8, 'tank2': 9.5}
    EFF_MOD = {'tank1': 8.0, 'tank2': 7.0}
    ERR_HIGH = 0.05
    ERR_DROP = 0.04
    SLOPE_DROP = -0.001
    SLOPE_FLAT = 0.0005

    def eval_tank(tank):
        sp = float(nominal_targets[tank])
        levels = [s[tank]['level'] for s in telemetry_window]
        efforts = [s[tank]['pump_effort'] for s in telemetry_window]
        n = len(levels)
        if n < 2:
            return False
        L = levels[-1]
        err_nom = sp - L
        k = min(10, n)
        if k > 1:
            slope = (levels[-1] - levels[-k]) / float(k - 1)
        else:
            slope = 0.0
        e_max = max(efforts[-k:]) if k > 0 else 0.0
        high_effort = (e_max >= EFF_HI[tank]) and (slope <= SLOPE_FLAT) and (err_nom > ERR_HIGH)
        early_drop = (slope < SLOPE_DROP) and (err_nom > ERR_DROP) and (e_max > EFF_MOD[tank])
        return bool(high_effort or early_drop)

    a1 = eval_tank('tank1')
    a2 = eval_tank('tank2')

    return {
        'diagnosis': 'tank1 anomaly=' + str(a1) + '; tank2 anomaly=' + str(a2),
        'adjusted_setpoints': {
            'tank1': float(nominal_targets['tank1']),
            'tank2': float(nominal_targets['tank2']),
        },
        'anomaly_flags': {'tank1': bool(a1), 'tank2': bool(a2)},
    }