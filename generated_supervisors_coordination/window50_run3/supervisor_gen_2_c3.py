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
        c1n = 0.25
        c2n = 0.25
        p1n = 0.80 * k1n
        p2n = 0.80 * k2n
        VMIN = 1.0
        VMAX = 12.0
        S1 = a1 * sq
        S2 = a2 * sq
        S3 = a3 * sq
        S4 = a4 * sq

        h1_act = float(active_setpoints['h1'])
        h2_act = float(active_setpoints['h2'])
        qt = float(objectives['production_target']) / 1000.0
        h2lo = float(objectives['h2_band'][0])
        h2hi = float(objectives['h2_band'][1])
        ulim = float(objectives['upper_level_limit'])
        spl = float(objectives['setpoint_limits'][0])
        sph = float(objectives['setpoint_limits'][1])

        w = telemetry_window
        n = len(w)
        if n < 6 or qt <= 0.0:
            return {'diagnosis': 'insufficient telemetry: holding setpoints',
                    'adjusted_setpoints': {'h1': h1_act, 'h2': h2_act}}

        tv = []
        h1v = []
        h2v = []
        h3v = []
        h4v = []
        f1v = []
        f2v = []
        f3v = []
        f4v = []
        sv1 = 0.0
        sv2 = 0.0
        for i in range(n):
            r = w[i]
            tv.append(float(r['time']))
            x = float(r['h1'])
            if x < 0.0:
                x = 0.0
            h1v.append(x)
            f1v.append(S1 * math.sqrt(x))
            x = float(r['h2'])
            if x < 0.0:
                x = 0.0
            h2v.append(x)
            f2v.append(S2 * math.sqrt(x))
            x = float(r['h3'])
            if x < 0.0:
                x = 0.0
            h3v.append(x)
            f3v.append(S3 * math.sqrt(x))
            x = float(r['h4'])
            if x < 0.0:
                x = 0.0
            h4v.append(x)
            f4v.append(S4 * math.sqrt(x))
            sv1 += float(r['v1'])
            sv2 += float(r['v2'])

        def _mean(xs):
            s = 0.0
            for v in xs:
                s += v
            return s / len(xs)

        def _slope(ys, ts):
            k = len(ys)
            st = 0.0
            sy = 0.0
            stt = 0.0
            sty = 0.0
            for i in range(k):
                st += ts[i]
                sy += ys[i]
                stt += ts[i] * ts[i]
                sty += ts[i] * ys[i]
            den = k * stt - st * st
            if abs(den) < 1.0e-9:
                return 0.0
            return (k * sty - st * sy) / den

        def _fit(xs, ys, cnom):
            k = len(xs)
            if k < 3:
                return (cnom, 0.0)
            mx = 0.0
            my = 0.0
            for v in xs:
                mx += v
            for v in ys:
                my += v
            mx /= k
            my /= k
            sxx = 0.0
            sxy = 0.0
            for i in range(k):
                dx = xs[i] - mx
                sxx += dx * dx
                sxy += dx * (ys[i] - my)
            if sxx < 1.0e-14 or sxx < k * (0.02 * mx) * (0.02 * mx):
                c = cnom
                d = my - c * mx
            else:
                c = sxy / sxx
                d = my - c * mx
            if c < 0.06:
                c = 0.06
            if c > 0.80:
                c = 0.80
            if d < -0.008:
                d = -0.008
            if d > 0.008:
                d = 0.008
            return (c, d)

        mf3 = _mean(f3v)
        mf4 = _mean(f4v)
        mv1 = sv1 / n
        mv2 = sv2 / n
        r2 = _slope(h2v, tv)
        r3 = _slope(h3v, tv)
        r4 = _slope(h4v, tv)

        if mv2 > 0.5:
            p2 = (r3 + mf3) / mv2
        else:
            p2 = p2n
        if mv1 > 0.5:
            p1 = (r4 + mf4) / mv1
        else:
            p1 = p1n
        if p1 < 0.4 * p1n:
            p1 = 0.4 * p1n
        if p1 > 1.7 * p1n:
            p1 = 1.7 * p1n
        if p2 < 0.4 * p2n:
            p2 = 0.4 * p2n
        if p2 > 1.7 * p2n:
            p2 = 1.7 * p2n

        nb = 5
        blk = n // nb
        x1s = []
        y1s = []
        x2s = []
        y2s = []
        if blk >= 4:
            for kb in range(nb):
                i0 = kb * blk
                i1 = i0 + blk - 1
                if i1 > n - 1:
                    i1 = n - 1
                dtb = tv[i1] - tv[i0]
                if dtb < 1.0:
                    dtb = 1.0
                cnt = i1 - i0 + 1
                sa = 0.0
                sb = 0.0
                sc = 0.0
                sd = 0.0
                for j in range(i0, i1 + 1):
                    sa += f1v[j]
                    sb += f2v[j]
                    sc += f3v[j]
                    sd += f4v[j]
                ma = sa / cnt
                mb = sb / cnt
                mc = sc / cnt
                md = sd / cnt
                y1s.append((h1v[i1] - h1v[i0]) / dtb + ma - mc)
                x1s.append(md)
                y2s.append((h2v[i1] - h2v[i0]) / dtb + mb - md)
                x2s.append(mc)

        c1, d1 = _fit(x1s, y1s, c1n)
        c2, d2 = _fit(x2s, y2s, c2n)

        den = 1.0 - c1 * c2
        if den < 0.2:
            den = 0.2
        A4 = (qt - d2 + c2 * d1) / den
        B4 = -(1.0 + c2) / den
        A3 = -d1 - c1 * A4
        B3 = 1.0 - c1 * B4
        if B3 < 0.2:
            B3 = 0.2

        lo = 0.0
        hi = 1.0e6

        cap3 = ulim - 0.03
        if cap3 < 0.08:
            cap3 = 0.08
        f3max = S3 * math.sqrt(cap3)
        if p2 * VMAX < f3max:
            f3max = p2 * VMAX
        b = (f3max - A3) / B3
        if b < hi:
            hi = b
        f3min = S3 * math.sqrt(0.02)
        if p2 * VMIN > f3min:
            f3min = p2 * VMIN
        b = (f3min - A3) / B3
        if b > lo:
            lo = b

        cap4 = ulim - 0.03
        if cap4 < 0.08:
            cap4 = 0.08
        f4max = S4 * math.sqrt(cap4)
        if p1 * VMAX < f4max:
            f4max = p1 * VMAX
        b = (f4max - A4) / B4
        if b > lo:
            lo = b
        f4min = S4 * math.sqrt(0.02)
        if p1 * VMIN > f4min:
            f4min = p1 * VMIN
        b = (f4min - A4) / B4
        if b < hi:
            hi = b

        f2hi = S2 * math.sqrt(h2hi)
        f2lo = S2 * math.sqrt(h2lo)
        b = qt - f2hi
        if b > lo:
            lo = b
        b = qt - f2lo
        if b < hi:
            hi = b
        tlo = h2lo + 0.01
        if tlo < 0.0:
            tlo = 0.0
        thi = h2hi - 0.01
        if thi > tlo:
            b = qt - S2 * math.sqrt(thi)
            if b > lo:
                lo = b
            b = qt - S2 * math.sqrt(tlo)
            if b < hi:
                hi = b

        b = S1 * math.sqrt(0.02)
        if b > lo:
            lo = b
        b = S1 * math.sqrt(1.45)
        if b < hi:
            hi = b
        b = qt - S2 * math.sqrt(1.45)
        if b > lo:
            lo = b
        b = qt - S2 * math.sqrt(0.02)
        if b < hi:
            hi = b

        sp0 = spl if spl > 0.0 else 0.0
        b = S1 * math.sqrt(sp0)
        if b > lo:
            lo = b
        b = S1 * math.sqrt(sph)
        if b < hi:
            hi = b
        b = qt - S2 * math.sqrt(sph)
        if b > lo:
            lo = b
        b = qt - S2 * math.sqrt(sp0)
        if b < hi:
            hi = b

        ha = h1_act if h1_act > 0.0 else 0.0
        hb = h2_act if h2_act > 0.0 else 0.0
        f1c = S1 * math.sqrt(ha)
        f2c = S2 * math.sqrt(hb)
        tot = f1c + f2c
        if tot > 1.0e-9:
            f1plan = (f1c / tot) * qt
        else:
            f1plan = 0.5 * qt

        h2m = h2v[n - 1]
        h3m = h3v[n - 1]
        h4m = h4v[n - 1]
        f3m = f3v[n - 1]
        f4m = f4v[n - 1]
        if ha > 1.0e-6:
            df1dh1 = S1 / (2.0 * math.sqrt(ha))
        else:
            df1dh1 = 0.0141

        soft3 = ulim - 0.03
        soft4 = ulim - 0.03
        Tp = 50.0
        up3 = h3m + (r3 * Tp if r3 > 0.0 else 0.0)
        up4 = h4m + (r4 * Tp if r4 > 0.0 else 0.0)
        e3 = up3 - soft3
        if e3 < 0.0:
            e3 = 0.0
        e4 = up4 - soft4
        if e4 < 0.0:
            e4 = 0.0
        e2h = (h2m + (r2 * 20.0 if r2 > 0.0 else 0.0)) - (h2hi - 0.01)
        if e2h < 0.0:
            e2h = 0.0
        e2l = (h2lo + 0.01) - (h2m + (r2 * 20.0 if r2 < 0.0 else 0.0))
        if e2l < 0.0:
            e2l = 0.0

        dtr = 0.0
        if e3 > 0.0 and f3m > 1.0e-6 and h3m > 1.0e-4:
            sens3 = 2.0 * h3m / f3m * B3
            if sens3 > 1.0e-6:
                dtr -= 0.45 * e3 / sens3
        if e4 > 0.0 and f4m > 1.0e-6 and h4m > 1.0e-4:
            sens4 = 2.0 * h4m / f4m * B4
            if sens4 < -1.0e-6:
                dtr -= 0.45 * e4 / sens4
        if h2m > 1.0e-6:
            k2s = 2.0 * math.sqrt(h2m) / S2
        else:
            k2s = 100.0
        if e2h > 0.0:
            dtr += 0.25 * e2h / k2s
        if e2l > 0.0:
            dtr -= 0.25 * e2l / k2s
        lim = 0.02 * df1dh1
        if dtr > lim:
            dtr = lim
        if dtr < -lim:
            dtr = -lim
        f1t = f1plan + dtr

        if hi < lo:
            f1s = 0.5 * (lo + hi)
            why = 'infeasible: upper-level or pump limits'
        else:
            f1s = f1t
            if f1s < lo:
                f1s = lo
                why = 'clamped to protect h3 or pump2'
            elif f1s > hi:
                f1s = hi
                why = 'clamped to protect h4 or pump1'
            elif dtr < -1.0e-9:
                why = 'quick trim: relieve high h3'
            elif dtr > 1.0e-9:
                why = 'quick trim: relieve high h4 or h2'
            else:
                why = 'split kept; Q on target'

        if f1s < 0.0:
            f1s = 0.0
        if f1s > qt:
            f1s = qt
        f2s = qt - f1s
        s1lo = S1 * math.sqrt(0.02)
        s1hi = S1 * math.sqrt(1.45)
        s2lo = S2 * math.sqrt(0.02)
        s2hi = S2 * math.sqrt(1.45)
        if f1s < s1lo:
            f1s = s1lo
            f2s = qt - f1s
        if f1s > s1hi:
            f1s = s1hi
            f2s = qt - f1s
        if f2s < s2lo:
            f2s = s2lo
            f1s = qt - f2s
        if f2s > s2hi:
            f2s = s2hi
            f1s = qt - f2s
        if f1s < 0.0:
            f1s = 0.0
        if f1s > qt:
            f1s = qt
        f2s = qt - f1s

        h1c = (f1s / S1) ** 2
        h2c = (f2s / S2) ** 2

        dh1 = h1c - h1_act
        dh2 = h2c - h2_act
        if dh1 > 0.10:
            dh1 = 0.10
        if dh1 < -0.10:
            dh1 = -0.10
        if dh2 > 0.10:
            dh2 = 0.10
        if dh2 < -0.10:
            dh2 = -0.10
        if abs(dh1) < 0.0025 and abs(dh2) < 0.0025:
            h1o = h1_act
            h2o = h2_act
        else:
            h1o = h1_act + dh1
            h2o = h2_act + dh2
        if h1o < spl:
            h1o = spl
        if h1o > sph:
            h1o = sph
        if h2o < spl:
            h2o = spl
        if h2o > sph:
            h2o = sph

        diag = ('Q*=' + str(round(qt * 1000.0, 2)) + ' L/s; d1=' +
                str(round(d1 * 1000.0, 2)) + ' d2=' + str(round(d2 * 1000.0, 2)) +
                ' L/s; p1=' + str(round(p1 / p1n, 2)) + ' p2=' +
                str(round(p2 / p2n, 2)) + ' x nom; c1=' + str(round(c1, 2)) +
                ' c2=' + str(round(c2, 2)) + '; ' + why)
        return {'diagnosis': diag,
                'adjusted_setpoints': {'h1': float(h1o), 'h2': float(h2o)}}
    except Exception:
        try:
            return {'diagnosis': 'fallback: holding setpoints',
                    'adjusted_setpoints': {'h1': float(active_setpoints['h1']),
                                           'h2': float(active_setpoints['h2'])}}
        except Exception:
            return {'diagnosis': 'fallback',
                    'adjusted_setpoints': {'h1': 0.30, 'h2': 0.35}}