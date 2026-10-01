def supervise(telemetry_window, active_setpoints, objectives):
    try:
        g = 9.81
        sq = math.sqrt(2.0 * g)
        a1 = 0.0035
        a2 = 0.0030
        a3 = 0.0020
        a4 = 0.0025
        k1n = 0.00085
        k2n = 0.00095
        gam1 = 0.20
        gam2 = 0.20
        c1 = gam1 / (1.0 - gam1)
        c2 = gam2 / (1.0 - gam2)
        p1n = (1.0 - gam1) * k1n
        p2n = (1.0 - gam2) * k2n
        den = 1.0 - c1 * c2
        VMIN = 1.0
        VMAX = 12.0

        h1_act = float(active_setpoints['h1'])
        h2_act = float(active_setpoints['h2'])
        target_prod = float(objectives['production_target'])
        qt = target_prod / 1000.0
        h2_lo_b = float(objectives['h2_band'][0])
        h2_hi_b = float(objectives['h2_band'][1])
        ulim = float(objectives['upper_level_limit'])
        sp_lo = float(objectives['setpoint_limits'][0])
        sp_hi = float(objectives['setpoint_limits'][1])

        w = telemetry_window
        n = len(w)
        if n < 10:
            return {'diagnosis': 'insufficient telemetry: holding setpoints',
                    'adjusted_setpoints': {'h1': h1_act, 'h2': h2_act}}

        m = min(10, n)
        ww = w[-m:]
        k = min(5, m)
        h1_recent = [float(r['h1']) for r in ww]
        h2_recent = [float(r['h2']) for r in ww]
        h3_recent = [float(r['h3']) for r in ww]
        h4_recent = [float(r['h4']) for r in ww]
        v1_recent = [float(r['v1']) for r in ww]
        v2_recent = [float(r['v2']) for r in ww]
        prod_recent = [float(r['production']) for r in ww]

        h1_m = sum(h1_recent[-k:]) / k
        h2_m = sum(h2_recent[-k:]) / k
        h3_m = sum(h3_recent[-k:]) / k
        h4_m = sum(h4_recent[-k:]) / k
        v1_m = sum(v1_recent[-k:]) / k
        v2_m = sum(v2_recent[-k:]) / k
        prod_m = sum(prod_recent[-k:]) / k

        F1_m = a1 * sq * math.sqrt(max(h1_m, 0.0))
        F2_m = a2 * sq * math.sqrt(max(h2_m, 0.0))
        u3_m = a3 * sq * math.sqrt(max(h3_m, 0.0))
        u4_m = a4 * sq * math.sqrt(max(h4_m, 0.0))

        if v2_m > 0.5:
            dh3_dt = (h3_recent[-1] - h3_recent[-k]) / (k - 1) if k > 1 else 0.0
            p2 = (dh3_dt + u3_m) / v2_m
        else:
            p2 = p2n
        if v1_m > 0.5:
            dh4_dt = (h4_recent[-1] - h4_recent[-k]) / (k - 1) if k > 1 else 0.0
            p1 = (dh4_dt + u4_m) / v1_m
        else:
            p1 = p1n
        p1 = max(0.5 * p1n, min(1.5 * p1n, p1))
        p2 = max(0.5 * p2n, min(1.5 * p2n, p2))

        d1_sum = 0.0
        d2_sum = 0.0
        cnt = 0
        start_idx = max(0, n - 6)
        for i in range(start_idx, n - 1):
            dt = float(w[i+1]['time']) - float(w[i]['time'])
            if dt < 0.5:
                continue
            h1_i = float(w[i]['h1'])
            h1_ip1 = float(w[i+1]['h1'])
            u3_i = a3 * sq * math.sqrt(max(float(w[i]['h3']), 0.0))
            u4_i = a4 * sq * math.sqrt(max(float(w[i]['h4']), 0.0))
            F1_i = a1 * sq * math.sqrt(max(h1_i, 0.0))
            d1_inst = (h1_ip1 - h1_i) / dt + F1_i - u3_i - c1 * u4_i
            d1_sum += d1_inst

            h2_i = float(w[i]['h2'])
            h2_ip1 = float(w[i+1]['h2'])
            F2_i = a2 * sq * math.sqrt(max(h2_i, 0.0))
            u4_i = a4 * sq * math.sqrt(max(float(w[i]['h4']), 0.0))
            u3_i = a3 * sq * math.sqrt(max(float(w[i]['h3']), 0.0))
            d2_inst = (h2_ip1 - h2_i) / dt + F2_i - u4_i - c2 * u3_i
            d2_sum += d2_inst
            cnt += 1
        if cnt > 0:
            d1 = d1_sum / cnt
            d2 = d2_sum / cnt
        else:
            d1 = 0.0
            d2 = 0.0
        d1 = max(-0.01, min(0.01, d1))
        d2 = max(-0.01, min(0.01, d2))

        rate3 = (h3_recent[-1] - h3_recent[0]) / (m - 1) if m > 1 else 0.0
        rate4 = (h4_recent[-1] - h4_recent[0]) / (m - 1) if m > 1 else 0.0

        base_m3 = 0.01
        if h3_recent[-1] > ulim - 0.02:
            base_m3 = 0.005
        else:
            base_m3 += max(0.0, rate3) * 5.0
        margin3 = min(0.06, max(0.005, base_m3))
        h3_max = ulim - margin3
        if h3_max < 0.05:
            h3_max = 0.05

        base_m4 = 0.01
        if h4_recent[-1] > ulim - 0.02:
            base_m4 = 0.005
        else:
            base_m4 += max(0.0, rate4) * 5.0
        margin4 = min(0.06, max(0.005, base_m4))
        h4_max = ulim - margin4
        if h4_max < 0.05:
            h4_max = 0.05

        v2_lim = VMAX - 0.1
        if v2_m > VMAX - 0.5:
            v2_lim = v2_m
        u3_cap = a3 * sq * math.sqrt(h3_max)
        u3_vmax = p2 * v2_lim
        u3_hi = min(u3_cap, u3_vmax)
        u3_lo = p2 * VMIN
        if v2_m > VMAX - 0.2:
            u3_hi = min(u3_hi, u3_m + 0.0002)

        v1_lim = VMAX - 0.1
        if v1_m > VMAX - 0.5:
            v1_lim = v1_m
        u4_cap = a4 * sq * math.sqrt(h4_max)
        u4_vmax = p1 * v1_lim
        u4_hi = min(u4_cap, u4_vmax)
        u4_lo = p1 * VMIN
        if v1_m > VMAX - 0.2:
            u4_hi = min(u4_hi, u4_m + 0.0002)

        Q_avg = prod_m
        Q_err = target_prod - Q_avg
        if abs(Q_err) < 0.05:
            Q_bias = 0.0
        else:
            Q_bias = 0.4 * Q_err
        Q_bias = max(-0.8, min(0.8, Q_bias))
        Q_eff_L = target_prod + Q_bias
        Q_eff = Q_eff_L / 1000.0

        def compute_interval(Q):
            lo = 0.0
            hi = 1e9
            b = (u3_hi * den + d1 + c1 * Q - c1 * d2) / (1.0 + c1)
            if b < hi: hi = b
            b = (u3_lo * den + d1 + c1 * Q - c1 * d2) / (1.0 + c1)
            if b > lo: lo = b
            b = (Q - d2 + c2 * d1 - u4_hi * den) / (1.0 + c2)
            if b > lo: lo = b
            b = (Q - d2 + c2 * d1 - u4_lo * den) / (1.0 + c2)
            if b < hi: hi = b
            b = Q - a2 * sq * math.sqrt(h2_hi_b)
            if b > lo: lo = b
            b = Q - a2 * sq * math.sqrt(h2_lo_b)
            if b < hi: hi = b
            b = a1 * sq * math.sqrt(0.02)
            if b > lo: lo = b
            b = a1 * sq * math.sqrt(1.45)
            if b < hi: hi = b
            if lo < 0.0: lo = 0.0
            if hi > Q: hi = Q
            return lo, hi

        lo, hi = compute_interval(Q_eff)
        if lo > hi:
            lo, hi = compute_interval(qt)
            if lo > hi:
                if h3_recent[-1] > ulim + 0.01:
                    F1_star = hi if hi > 0 else lo
                elif h4_recent[-1] > ulim + 0.01:
                    F1_star = lo
                else:
                    F1_star = (lo + hi) / 2.0
                Q_use = qt
            else:
                Q_use = qt
        else:
            Q_use = Q_eff

        if lo <= hi:
            best_F1 = None
            best_cost = 1e9
            steps = 100
            for i in range(steps + 1):
                F1_cand = lo + (hi - lo) * i / steps
                if F1_cand < 0.0: continue
                if F1_cand > Q_use: continue
                F2_cand = Q_use - F1_cand
                if F2_cand < 0.0: continue
                h1_cand = (F1_cand / (a1 * sq)) ** 2
                h2_cand = (F2_cand / (a2 * sq)) ** 2
                cost = abs(h1_cand - h1_act) + abs(h2_cand - h2_act)
                if cost < best_cost:
                    best_cost = cost
                    best_F1 = F1_cand
            if best_F1 is None:
                F1_star = (lo + hi) / 2.0
            else:
                F1_star = best_F1

        if F1_star < 0.0: F1_star = 0.0
        if F1_star > Q_use: F1_star = Q_use
        F2_star = Q_use - F1_star
        if F2_star < 0.0: F2_star = 0.0

        h1_new = (F1_star / (a1 * sq)) ** 2
        h2_new = (F2_star / (a2 * sq)) ** 2

        if h1_new < sp_lo: h1_new = sp_lo
        if h1_new > sp_hi: h1_new = sp_hi
        if h2_new < sp_lo: h2_new = sp_lo
        if h2_new > sp_hi: h2_new = sp_hi

        if h1_new < 0.02: h1_new = 0.02
        if h1_new > 1.45: h1_new = 1.45
        if h2_new < 0.02: h2_new = 0.02
        if h2_new > 1.45: h2_new = 1.45

        max_step = 0.04
        dh1 = h1_new - h1_act
        dh2 = h2_new - h2_act
        if abs(dh1) > max_step:
            h1_new = h1_act + max_step * (1.0 if dh1 > 0 else -1.0)
        if abs(dh2) > max_step:
            h2_new = h2_act + max_step * (1.0 if dh2 > 0 else -1.0)
        if abs(h1_new - h1_act) < 0.003 and abs(h2_new - h2_act) < 0.003:
            h1_new = h1_act
            h2_new = h2_act

        diag = ('Q*=' + str(round(target_prod, 2)) + ' L/s, Q_eff=' + str(round(Q_use * 1000.0, 2)) +
                ' d1=' + str(round(d1 * 1000.0, 2)) + ' d2=' + str(round(d2 * 1000.0, 2)) +
                ' L/s, p1=' + str(round(p1 / p1n, 2)) + ' p2=' + str(round(p2 / p2n, 2)) +
                'x nom, h3_max=' + str(round(h3_max, 3)) + ' h4_max=' + str(round(h4_max, 3)))
        return {'diagnosis': diag,
                'adjusted_setpoints': {'h1': float(h1_new), 'h2': float(h2_new)}}
    except Exception:
        try:
            return {'diagnosis': 'fallback: holding setpoints',
                    'adjusted_setpoints': {'h1': float(active_setpoints['h1']),
                                           'h2': float(active_setpoints['h2'])}}
        except Exception:
            return {'diagnosis': 'fallback',
                    'adjusted_setpoints': {'h1': 0.30, 'h2': 0.35}}