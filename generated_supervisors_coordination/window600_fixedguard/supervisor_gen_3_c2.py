def supervise(telemetry_window, active_setpoints, objectives):
    G = 9.81
    a1 = 0.0035; a2 = 0.003; a3 = 0.002; a4 = 0.0025
    c3n = 0.00076; c4n = 0.00068
    R0 = 0.25
    DEN = 1.0 - R0*R0
    VMAX = 12.0
    fallback = {'diagnosis': 'fallback: hold previous setpoints',
                'adjusted_setpoints': {'h1': float(active_setpoints['h1']),
                                       'h2': float(active_setpoints['h2'])}}
    tw = telemetry_window
    n = len(tw)
    if n < 6:
        return fallback
    try:
        lo_lim, hi_lim = objectives['setpoint_limits']
        lo_lim = float(lo_lim); hi_lim = float(hi_lim)
        Hup = float(objectives['upper_level_limit'])
        h2lo = float(objectives['h2_band'][0]); h2hi = float(objectives['h2_band'][1])
        Qt = float(objectives['production_target']) / 1000.0
        if Qt <= 0.0:
            return fallback

        def sg(x):
            return math.sqrt(2.0*G*x) if x > 0.0 else 0.0

        Y1=[]; Y2=[]; Y3=[]; Y4=[]; V1=[]; V2=[]; Q3=[]; Q4=[]
        for i in range(1, n):
            p = tw[i]; m = tw[i-1]
            h1=p['h1']; h2=p['h2']; h3=p['h3']; h4=p['h4']
            v1=p['v1']; v2=p['v2']
            q1=a1*sg(h1); q2=a2*sg(h2); q3=a3*sg(h3); q4=a4*sg(h4)
            Y1.append((h1-m['h1']) + q1 - q3)
            Y2.append((h2-m['h2']) + q2 - q4)
            Y3.append((h3-m['h3']) + q3)
            Y4.append((h4-m['h4']) + q4)
            V1.append(v1); V2.append(v2); Q3.append(q3); Q4.append(q4)
        N = len(Y1)
        if N < 4:
            return fallback

        i0 = max(0, N-180)
        def reg0(vs, ys):
            num=0.0; den=0.0
            for k in range(i0, N):
                num += vs[k]*ys[k]; den += vs[k]*vs[k]
            if den < 1e-5:
                return None
            return num/den
        def medratio(qs, vs):
            a=[]
            for k in range(i0, N):
                if vs[k] > 2.0:
                    a.append(qs[k]/vs[k])
            if not a:
                return None
            a.sort(); return a[len(a)//2]

        c3 = reg0(V2, Y3)
        if c3 is None or c3 < 0.3*c3n or c3 > 3.0*c3n:
            mr = medratio(Q3, V2); c3 = mr if mr else c3n
        c4 = reg0(V1, Y4)
        if c4 is None or c4 < 0.3*c4n or c4 > 3.0*c4n:
            mr = medratio(Q4, V1); c4 = mr if mr else c4n
        if not (c3 > 0): c3 = c3n
        if not (c4 > 0): c4 = c4n

        d1s=[]; d2s=[]
        for k in range(N):
            d1s.append(Y1[k] - R0*c4*V1[k])
            d2s.append(Y2[k] - R0*c3*V2[k])
        NE = min(N, 360); j0 = N-NE
        e1 = d1s[j0:]; e2 = d2s[j0:]
        e1.sort(); e2.sort()
        def tr(a):
            m=len(a)
            if m < 8:
                return a[0], a[-1]
            lo=int(m*0.02); hi=m-1-int(m*0.02)
            if hi<=lo:
                lo=0; hi=m-1
            return a[lo], a[hi]
        d1lo,d1hi = tr(e1); d2lo,d2hi = tr(e2)
        dm=0.00008
        d1lo-=dm; d1hi+=dm; d2lo-=dm; d2hi+=dm

        hm=0.02; vm=0.6; h2m=0.008
        q3max = min(a3*sg(max(Hup-hm,0.05)), c3*(VMAX-vm))
        q4max = min(a4*sg(max(Hup-hm,0.05)), c4*(VMAX-vm))
        x3max = (q3max*DEN + d1lo + R0*Qt - R0*d2hi)/(1.0+R0)
        x4min = (Qt - d2lo + R0*d1hi - q4max*DEN)/(1.0+R0)
        x_h2lo = Qt - a2*sg(h2hi-h2m)
        x_h2hi = Qt - a2*sg(h2lo+h2m)
        s1min = max(lo_lim, 0.02); s1max = min(hi_lim, 1.5)
        x_s1lo = a1*sg(s1min); x_s1hi = a1*sg(s1max)

        sp1 = min(max(float(active_setpoints['h1']), lo_lim), hi_lim)
        sp2 = min(max(float(active_setpoints['h2']), lo_lim), hi_lim)

        xg_lo = max(0.0, x_s1lo)
        xg_hi = min(x_s1hi, Qt*0.999)
        if xg_hi <= xg_lo + 1e-9:
            return fallback

        NG = 480
        best = None
        span = xg_hi - xg_lo
        for gi in range(NG+1):
            x = xg_lo + span*gi/NG
            rem = Qt - x
            if rem <= 1e-6:
                continue
            s1 = (x/a1)*(x/a1)/(2.0*G)
            s2 = (rem/a2)*(rem/a2)/(2.0*G)
            if s1 < s1min-1e-9 or s1 > s1max+1e-9:
                continue
            q3 = (x - d1lo - R0*(rem - d2hi))/DEN
            q4 = (rem - d2lo - R0*(x - d1hi))/DEN
            pen = 0.0
            if q3 > q3max: pen += (q3-q3max)/q3max
            if q4 > q4max: pen += (q4-q4max)/q4max
            if s2 > h2hi-h2m: pen += (s2-(h2hi-h2m))/h2hi
            if s2 < h2lo+h2m: pen += ((h2lo+h2m)-s2)/h2hi
            if q3 < 0.0: pen += (-q3)/q3max
            if q4 < 0.0: pen += (-q4)/q4max
            travel = abs(s1-sp1) + abs(s2-sp2)
            cost = 2000.0*pen + travel
            if best is None or cost < best[0]:
                best = (cost, s1, s2, pen, travel)
        if best is None:
            return fallback
        _, s1b, s2b, pen, travel = best
        if pen < 1e-9 and travel < 0.004:
            return {'diagnosis': 'on target; constraints satisfied, holding setpoints',
                    'adjusted_setpoints': {'h1': sp1, 'h2': sp2}}
        dl = 0.12
        if s1b - sp1 > dl: s1b = sp1 + dl
        elif sp1 - s1b > dl: s1b = sp1 - dl
        if s2b - sp2 > dl: s2b = sp2 + dl
        elif sp2 - s2b > dl: s2b = sp2 - dl
        s1b = min(max(s1b, lo_lim), hi_lim)
        s2b = min(max(s2b, lo_lim), hi_lim)
        if pen > 1e-9:
            diag = 'best effort: limits partly infeasible; shift split toward relieving upper tanks'
        else:
            diag = 'shifted production split to keep h3,h4 and pump voltages inside margins while holding Q on target'
        return {'diagnosis': diag, 'adjusted_setpoints': {'h1': float(s1b), 'h2': float(s2b)}}
    except Exception:
        return fallback
