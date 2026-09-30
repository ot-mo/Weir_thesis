def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    sp1 = active_setpoints['tank1']
    sp2 = active_setpoints['tank2']
    nom1 = nominal_targets['tank1']
    nom2 = nominal_targets['tank2']

    if n < 12:
        return {
            'diagnosis': 'insufficient telemetry',
            'adjusted_setpoints': {'tank1': sp1, 'tank2': sp2},
            'anomaly_flags': {'tank1': False, 'tank2': False},
        }

    RAIL_V = 11.4
    RAIL_N = 1
    MID2 = 10.0
    ERR_TH = 0.07
    RISE_FAST = 0.0012
    LOOK = 10
    RISE_SPAN = 3
    SP_STEP = 0.02
    SP_DROP = 0.04
    SP_MIN = 0.05
    SP_MAX = 0.48

    def col(tank, field):
        return [step[tank][field] for step in telemetry_window]

    def detect(tank, other):
        eff = col(tank, 'pump_effort')
        lvl = col(tank, 'level')
        err = col(tank, 'error')

        cnt_rail = 0
        for v in eff[-LOOK:]:
            if v >= RAIL_V:
                cnt_rail += 1

        mid_anomaly = False
        if tank == 'tank2':
            cnt_mid = 0
            for v in eff[-LOOK:]:
                if v >= MID2:
                    cnt_mid += 1
            err_ok = abs(err[-1]) >= ERR_TH
            other_eff = col(other, 'pump_effort')
            span = 5
            if span > n - 1:
                span = n - 1
            acc = 0.0
            for i in range(n - span, n):
                acc += other_eff[i] - other_eff[i - 1]
            other_slope = acc / float(span)
            recovering_other = (other_eff[-1] >= 11.0 and other_slope < -0.02)
            mid_anomaly = (cnt_mid >= 1 and err_ok and not recovering_other)

        span = RISE_SPAN
        if span > n - 1:
            span = n - 1
        acc = 0.0
        for i in range(n - span, n):
            acc += lvl[i] - lvl[i - 1]
        rate = acc / float(span)
        refilling = rate > RISE_FAST

        anomaly = ((cnt_rail >= RAIL_N) or mid_anomaly) and not refilling
        return anomaly, cnt_rail, mid_anomaly, rate

    a1, c1, m1, r1 = detect('tank1', 'tank2')
    a2, c2, m2, r2 = detect('tank2', 'tank1')

    def next_sp(sp, nom, anomaly):
        lo = nom - SP_DROP
        if lo < SP_MIN:
            lo = SP_MIN
        if anomaly:
            new = sp - SP_STEP
            if new < lo:
                new = lo
        else:
            new = sp + SP_STEP
            if new > nom:
                new = nom
        if new < SP_MIN:
            new = SP_MIN
        if new > SP_MAX:
            new = SP_MAX
        return round(new, 4)

    sp1n = next_sp(sp1, nom1, a1)
    sp2n = next_sp(sp2, nom2, a2)

    diag = ('tank1: flag={} rail={}/10 mid={} dLdt={:+.4f} | '
            'tank2: flag={} rail={}/10 mid={} dLdt={:+.4f}').format(
        a1, c1, m1, r1, a2, c2, m2, r2)

    return {
        'diagnosis': diag,
        'adjusted_setpoints': {'tank1': sp1n, 'tank2': sp2n},
        'anomaly_flags': {'tank1': a1, 'tank2': a2},
    }