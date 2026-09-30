def supervise(telemetry_window, active_setpoints, nominal_targets):
    EFF_SAT = {'tank1': 11.0, 'tank2': 9.7}
    DROP5 = -0.0025
    DROP10 = -0.0018
    RECOV5 = 0.0030

    def eval_tank(t):
        sp = float(nominal_targets[t])
        lv = [s[t]['level'] for s in telemetry_window]
        ef = [s[t]['pump_effort'] for s in telemetry_window]
        n = len(lv)
        if n == 0:
            return False
        L = lv[-1]
        err = sp - L
        k10 = 10 if n >= 11 else n - 1
        k5 = 5 if n >= 6 else n - 1
        slope10 = (L - lv[-1 - k10]) / float(k10) if k10 > 0 else 0.0
        slope5 = (L - lv[-1 - k5]) / float(k5) if k5 > 0 else 0.0
        emax = max(ef[-10:]) if n >= 10 else max(ef)

        sat = emax >= EFF_SAT[t]
        drop = (slope5 <= DROP5) and (err > 0.03) and (L < sp - 0.02)
        slow = (slope10 <= DROP10) and (err > 0.05) and (L < sp - 0.03)
        recov = slope5 >= RECOV5
        flag = (sat or drop or slow) and not recov
        return bool(flag)

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