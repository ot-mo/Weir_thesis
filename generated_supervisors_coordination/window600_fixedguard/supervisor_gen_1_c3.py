def supervise(telemetry_window, active_setpoints, objectives):
    try:
        s2g = math.sqrt(2.0 * 9.81)
        a1 = 0.0035
        a2 = 0.003
        a3 = 0.002
        a4 = 0.0025
        g1 = 0.20
        g2 = 0.20
        c2n = (1.0 - g1) * 0.00085
        c3n = (1.0 - g2) * 0.00095
        r1 = g1 / (1.0 - g1)
        r2 = g2 / (1.0 - g2)
        n = len(telemetry_window)
        cur = telemetry_window[n - 1]
        h1 = float(cur['h1'])
        h2c = float(cur['h2'])
        h3 = float(cur['h3'])
        h4 = float(cur['h4'])
        v1 = float(cur['v1'])
        v2 = float(cur['v2'])
        tgt = float(objectives['production_target'])
        Qm = tgt / 1000.0
        band = objectives['h2_band']
        blo = float(band[0])
        bhi = float(band[1])
        ulim = float(objectives['upper_level_limit'])
        sl = objectives['setpoint_limits']
        slo = float(sl[0])
        shi = float(sl[1])
        M = 120
        if M > n:
            M = n
        seg = telemetry_window[n - M:]
        sv1 = 0.0
        sv2 = 0.0
        ss3 = 0.0
        ss4 = 0.0
        for s in seg:
            sv1 += float(s['v1'])
            sv2 += float(s['v2'])
            ss3 += math.sqrt(max(0.0, float(s['h3'])))
            ss4 += math.sqrt(max(0.0, float(s['h4'])))
        dh3w = float(seg[-1]['h3']) - float(seg[0]['h3'])
        dh4w = float(seg[-1]['h4']) - float(seg[0]['h4'])
        if sv2 > 1.0:
            c3 = (dh3w + a3 * s2g * ss3) / sv2
        else:
            c3 = a3 * s2g * math.sqrt(max(h3, 1e-9)) / max(v2, 0.5)
        if sv1 > 1.0:
            c2 = (dh4w + a4 * s2g * ss4) / sv1
        else:
            c2 = a4 * s2g * math.sqrt(max(h4, 1e-9)) / max(v1, 0.5)
        if c3 < 0.3 * c3n:
            c3 = 0.3 * c3n
        if c3 > 2.2 * c3n:
            c3 = 2.2 * c3n
        if c2 < 0.3 * c2n:
            c2 = 0.3 * c2n
        if c2 > 2.2 * c2n:
            c2 = 2.2 * c2n
        p1 = r1 * c2
        p4 = r2 * c3
        det = p1 * p4 - c3 * c2
        if abs(det) < 1e-13:
            det = -1e-9
        k = 10
        if k > n - 1:
            k = n - 1
        dh1dt = (h1 - float(telemetry_window[n - 1 - k]['h1'])) / k
        dh2dt = (h2c - float(telemetry_window[n - 1 - k]['h2'])) / k
        q1 = a1 * s2g * math.sqrt(max(h1, 1e-9))
        q2 = a2 * s2g * math.sqrt(max(h2c, 1e-9))
        d1 = dh1dt + q1 - a3 * s2g * math.sqrt(max(h3, 1e-9)) - p1 * v1
        d2 = dh2dt + q2 - a4 * s2g * math.sqrt(max(h4, 1e-9)) - p4 * v2
        h3eff = ulim - 0.04
        h4eff = ulim - 0.04
        h2lo = blo + 0.003
        h2hi = bhi - 0.003
        if h2lo < slo:
            h2lo = slo
        if h2hi > shi:
            h2hi = shi
        if h2hi < h2lo:
            h2lo = (blo + bhi) / 2.0
            h2hi = h2lo
        ah1 = float(active_setpoints['h1'])
        ah2 = float(active_setpoints['h2'])
        best_cost = 1e18
        bh1 = ah1
        bh2 = ah2
        bh3 = h3
        bh4 = h4
        nsteps = int((h2hi - h2lo) / 0.002) + 1
        i = 0
        while i <= nsteps:
            ch2 = h2lo + 0.002 * i
            i += 1
            if ch2 > h2hi:
                ch2 = h2hi
            q2n = a2 * s2g * math.sqrt(max(ch2, 1e-9))
            q1n = Qm - q2n
            if q1n <= 1e-9:
                continue
            ch1 = (q1n / (a1 * s2g)) ** 2
            b1 = q1n - d1
            b2 = q2n - d2
            v1n = (p4 * b1 - c3 * b2) / det
            v2n = (-c2 * b1 + p1 * b2) / det
            excess = 0.0
            h3n = h3
            h4n = h4
            if v1n > 1e-6 and v2n > 1e-6:
                h3n = (c3 * v2n / (a3 * s2g)) ** 2
                h4n = (c2 * v1n / (a4 * s2g)) ** 2
                if h3n > h3eff:
                    excess += h3n - h3eff
                if h4n > h4eff:
                    excess += h4n - h4eff
            else:
                excess += 1.0
            if v1n > 12.0:
                excess += (v1n - 12.0) * 0.05
            if v2n > 12.0:
                excess += (v2n - 12.0) * 0.05
            if v1n < 1.0:
                excess += (1.0 - v1n) * 0.05
            if v2n < 1.0:
                excess += (1.0 - v2n) * 0.05
            if ch1 < 0.02:
                excess += (0.02 - ch1) * 2.0
            if ch1 > 1.5:
                excess += (ch1 - 1.5) * 2.0
            travel = abs(ch1 - ah1) + abs(ch2 - ah2)
            cost = excess * 40.0 + travel
            if cost < best_cost:
                best_cost = cost
                bh1 = ch1
                bh2 = ch2
                bh3 = h3n
                bh4 = h4n
        if abs(bh1 - ah1) < 0.004 and abs(bh2 - ah2) < 0.004:
            oh1 = ah1
            oh2 = ah2
        else:
            oh1 = round(bh1 / 0.002) * 0.002
            oh2 = round(bh2 / 0.002) * 0.002
        if oh1 < slo:
            oh1 = slo
        if oh1 > shi:
            oh1 = shi
        if oh2 < slo:
            oh2 = slo
        if oh2 > shi:
            oh2 = shi
        if oh2 < blo:
            oh2 = blo
        if oh2 > bhi:
            oh2 = bhi
        diag = 'Qtarget=%.2f L/s set h1=%.3f h2=%.3f pred h3=%.3f h4=%.3f c2=%.5f c3=%.5f d1=%.5f d2=%.5f' % (tgt, oh1, oh2, bh3, bh4, c2, c3, d1, d2)
        return {'diagnosis': diag, 'adjusted_setpoints': {'h1': float(oh1), 'h2': float(oh2)}}
    except Exception:
        return {'diagnosis': 'fallback hold', 'adjusted_setpoints': {'h1': float(active_setpoints['h1']), 'h2': float(active_setpoints['h2'])}}