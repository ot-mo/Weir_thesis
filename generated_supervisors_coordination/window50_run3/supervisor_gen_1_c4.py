def supervise(telemetry_window, active_setpoints, objectives):
    try:
        a1 = 0.0035
        a2 = 0.0030
        a3 = 0.0020
        a4 = 0.0025
        u1n = 0.00068
        u2n = 0.00076
        tg = 19.62

        def flow(a, h):
            if h <= 0.0:
                return 0.0
            return a * math.sqrt(tg * h)

        QL = float(objectives['production_target'])
        Qt = QL / 1000.0
        h2lo = float(objectives['h2_band'][0])
        h2hi = float(objectives['h2_band'][1])
        ulim = float(objectives['upper_level_limit'])
        splo = float(objectives['setpoint_limits'][0])
        sphi = float(objectives['setpoint_limits'][1])
        h1a = float(active_setpoints['h1'])
        h2a = float(active_setpoints['h2'])

        u1 = u1n
        u2 = u2n
        d1 = 0.0
        d2 = 0.0
        try:
            n = len(telemetry_window)
            m = 10
            if m > n - 1:
                m = n - 1
            if m >= 1:
                s1 = 0.0
                s2 = 0.0
                sd1 = 0.0
                sd2 = 0.0
                cnt = 0
                for i in range(n - m, n):
                    c = telemetry_window[i]
                    p = telemetry_window[i - 1]
                    dt = float(c['time']) - float(p['time'])
                    if dt <= 0.0:
                        dt = 1.0
                    ch1 = float(c['h1'])
                    ch2 = float(c['h2'])
                    ch3 = float(c['h3'])
                    ch4 = float(c['h4'])
                    dh1 = (ch1 - float(p['h1'])) / dt
                    dh2 = (ch2 - float(p['h2'])) / dt
                    dh3 = (ch3 - float(p['h3'])) / dt
                    dh4 = (ch4 - float(p['h4'])) / dt
                    v1c = float(c['v1'])
                    v2c = float(c['v2'])
                    if v1c < 0.5:
                        v1c = 0.5
                    if v2c < 0.5:
                        v2c = 0.5
                    u2i = (dh3 + flow(a3, ch3)) / v2c
                    u1i = (dh4 + flow(a4, ch4)) / v1c
                    if u2i < 0.6 * u2n:
                        u2i = 0.6 * u2n
                    elif u2i > 1.6 * u2n:
                        u2i = 1.6 * u2n
                    if u1i < 0.6 * u1n:
                        u1i = 0.6 * u1n
                    elif u1i > 1.6 * u1n:
                        u1i = 1.6 * u1n
                    s1 += u1i
                    s2 += u2i
                    sd1 += dh1 + flow(a1, ch1) - u2i * v2c - 0.25 * u1i * v1c
                    sd2 += dh2 + flow(a2, ch2) - u1i * v1c - 0.25 * u2i * v2c
                    cnt += 1
                if cnt > 0:
                    u1 = s1 / cnt
                    u2 = s2 / cnt
                    d1 = sd1 / cnt
                    d2 = sd2 / cnt
        except Exception:
            u1 = u1n
            u2 = u2n
            d1 = 0.0
            d2 = 0.0

        if d1 < -0.006:
            d1 = -0.006
        elif d1 > 0.006:
            d1 = 0.006
        if d2 < -0.006:
            d2 = -0.006
        elif d2 > 0.006:
            d2 = 0.006

        def predict(x, y):
            q1 = flow(a1, x)
            q2 = flow(a2, y)
            Sc = q1 + q2 - d1 - d2
            u1v1 = (0.8 * Sc - q1 + d1) / 0.75
            v1s = u1v1 / u1
            u2v2 = 0.8 * Sc - u1v1
            v2s = u2v2 / u2
            if v1s < 0.0:
                v1s = 0.0
            if v2s < 0.0:
                v2s = 0.0
            h3s = (u2 * v2s / a3) ** 2 / tg
            h4s = (u1 * v1s / a4) ** 2 / tg
            return v1s, v2s, h3s, h4s

        def cost_of(x, y):
            v1s, v2s, h3s, h4s = predict(x, y)
            c = 100.0 * (abs(x - h1a) + abs(y - h2a))
            c += 300.0 * abs(1000.0 * (flow(a1, x) + flow(a2, y)) - QL)
            c += 3000.0 * (max(0.0, y - h2hi) + max(0.0, h2lo - y))
            c += 3000.0 * (max(0.0, h3s - (ulim - 0.02)) + max(0.0, h4s - (ulim - 0.02)))
            c += 100000.0 * (max(0.0, y - 1.40) + max(0.0, 0.03 - y))
            c += 100000.0 * (max(0.0, x - 1.40) + max(0.0, 0.03 - x))
            c += 1000.0 * (max(0.0, v1s - 11.6) + max(0.0, v2s - 11.6))
            c += 1000.0 * (max(0.0, 1.0 - v1s) + max(0.0, 1.0 - v2s))
            return c

        xlo = splo
        if xlo < 0.03:
            xlo = 0.03
        xhi = sphi
        if xhi > 1.30:
            xhi = 1.30

        best_x = None
        best_y = None
        best_c = None
        N = int((xhi - xlo) / 0.005)
        for k in range(N + 1):
            x = xlo + k * 0.005
            q1 = flow(a1, x)
            q2 = Qt - q1
            if q2 > 0.0:
                y = (q2 / a2) ** 2 / tg
                if y >= splo and y <= sphi:
                    c = cost_of(x, y)
                    if best_c is None or c < best_c:
                        best_c = c
                        best_x = x
                        best_y = y

        c = cost_of(h1a, h2a)
        if best_c is None or c < best_c:
            best_c = c
            best_x = h1a
            best_y = h2a

        if best_x < splo:
            best_x = splo
        if best_x > sphi:
            best_x = sphi
        if best_y < splo:
            best_y = splo
        if best_y > sphi:
            best_y = sphi

        if abs(best_x - h1a) + abs(best_y - h2a) < 0.003:
            best_x = h1a
            best_y = h2a

        best_x = round(best_x, 3)
        best_y = round(best_y, 3)
        diag = 'Q_t=%.2f d1=%.2f d2=%.2f sp=(%.3f, %.3f)' % (QL, d1 * 1000.0, d2 * 1000.0, best_x, best_y)
        return {'diagnosis': diag, 'adjusted_setpoints': {'h1': best_x, 'h2': best_y}}
    except Exception:
        return {'diagnosis': 'fallback nominal', 'adjusted_setpoints': {'h1': 0.30, 'h2': 0.35}}
