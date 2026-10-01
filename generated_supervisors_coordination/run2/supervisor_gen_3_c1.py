def supervise(telemetry_window, active_setpoints, objectives):
    try:
        a1=0.0035; a2=0.003; a3=0.002; a4=0.0025
        A1=A2=A3=A4=1.0
        gamma1=0.20; gamma2=0.20
        g=9.81
        Q_t = float(objectives["production_target"])
        h2_low, h2_high = objectives["h2_band"]
        upper_lim = float(objectives["upper_level_limit"])
        sp_lo, sp_hi = objectives["setpoint_limits"]
        h2_low = float(h2_low); h2_high = float(h2_high)
        sp_lo = float(sp_lo); sp_hi = float(sp_hi)
        n = len(telemetry_window)
        if n < 5:
            return {"diagnosis":"window too short","adjusted_setpoints":{"h1":float(active_setpoints["h1"]),"h2":float(active_setpoints["h2"])}}
        k = min(12, n)
        win = telemetry_window[-k:]
        ts = [float(s["time"]) for s in win]
        h1s = [float(s["h1"]) for s in win]
        h2s = [float(s["h2"]) for s in win]
        h3s = [float(s["h3"]) for s in win]
        h4s = [float(s["h4"]) for s in win]
        v1s = [float(s["v1"]) for s in win]
        v2s = [float(s["v2"]) for s in win]
        qs = [float(s["production"]) for s in win]
        def mean(xs): return sum(xs)/len(xs)
        def slope(ys, ts):
            m = len(ys)
            if m < 2: return 0.0
            mt = sum(ts)/m; my = sum(ys)/m
            num = 0.0; den = 0.0
            for i in range(m):
                dt = ts[i]-mt
                num += dt*(ys[i]-my)
                den += dt*dt
            if den < 1e-12: return 0.0
            return num/den
        mh1=mean(h1s); mh2=mean(h2s); mh3=mean(h3s); mh4=mean(h4s)
        mv1=mean(v1s); mv2=mean(v2s)
        dh1=slope(h1s,ts); dh2=slope(h2s,ts); dh3=slope(h3s,ts); dh4=slope(h4s,ts)
        def qf(h, a):
            if h <= 0.0: return 0.0
            return 1000.0*a*math.sqrt(2.0*g*h)
        def hf(q, a):
            if q <= 0.0: return 0.0
            return (q/(1000.0*a))**2/(2.0*g)
        mq1=qf(mh1,a1); mq2=qf(mh2,a2); mq3=qf(mh3,a3); mq4=qf(mh4,a4)
        if mv1 > 0.5:
            B_eff = (mq4 + 1000.0*A4*dh4)/mv1
        else:
            B_eff = (1.0-gamma1)*0.85
        if mv2 > 0.5:
            D_eff = (mq3 + 1000.0*A3*dh3)/mv2
        else:
            D_eff = (1.0-gamma2)*0.95
        B_eff = min(max(B_eff, 0.05), 1.5)
        D_eff = min(max(D_eff, 0.05), 1.5)
        alpha = gamma1/(1.0-gamma1)
        beta = gamma2/(1.0-gamma2)
        A_eff = alpha*B_eff
        C_eff = beta*D_eff
        d1_est = 1000.0*A1*dh1 + mq1 - mq3 - A_eff*mv1
        d2_est = 1000.0*A2*dh2 + mq2 - mq4 - C_eff*mv2
        h1c = h1s[-1]; h2c = h2s[-1]; h3c = h3s[-1]; h4c = h4s[-1]
        v1c = v1s[-1]; v2c = v2s[-1]
        Q_actual = mean(qs)
        Q_err = Q_t - Q_actual
        Q_eff = Q_t + 0.8*Q_err
        if Q_eff > Q_t + 2.0: Q_eff = Q_t + 2.0
        if Q_eff < Q_t - 2.0: Q_eff = Q_t - 2.0
        excess3 = max(0.0, h3c - upper_lim)
        excess4 = max(0.0, h4c - upper_lim)
        excess_v2 = max(0.0, v2c - 11.5)
        excess_v1 = max(0.0, v1c - 11.5)
        def evaluate(h1_sp):
            if h1_sp < 0.02 or h1_sp > 1.5:
                return None
            q1 = qf(h1_sp, a1)
            q2 = Q_eff - q1
            if q2 <= 0.05:
                return None
            h2_sp = hf(q2, a2)
            if h2_sp < 0.02 or h2_sp > 1.5:
                return None
            rhs1 = q1 - d1_est
            rhs2 = q2 - d2_est
            det = 1.0 - alpha*beta
            q3 = (rhs1 - alpha*rhs2)/det
            q4 = (rhs2 - beta*rhs1)/det
            q3 = max(q3, 0.0)
            q4 = max(q4, 0.0)
            h3 = hf(q3, a3)
            h4 = hf(q4, a4)
            v1 = q4/B_eff if B_eff > 0.05 else 12.0
            v2 = q3/D_eff if D_eff > 0.05 else 12.0
            travel = abs(h1_sp - active_setpoints["h1"]) + abs(h2_sp - active_setpoints["h2"])
            cost = 100.0*travel
            if h3 > upper_lim:
                cost += 20000.0*(h3-upper_lim)
            elif h3 > upper_lim - 0.05:
                cost += 2000.0*(h3 - (upper_lim-0.05))
            if h4 > upper_lim:
                cost += 20000.0*(h4-upper_lim)
            elif h4 > upper_lim - 0.05:
                cost += 2000.0*(h4 - (upper_lim-0.05))
            for vv in (v1,v2):
                if vv > 12.0:
                    cost += 20000.0*(vv-12.0)
                elif vv > 11.2:
                    cost += 2000.0*(vv-11.2)
                if vv < 1.0:
                    cost += 20000.0*(1.0-vv)
            if h2_sp < h2_low:
                cost += 5000.0*(h2_low - h2_sp)
            elif h2_sp > h2_high:
                cost += 5000.0*(h2_sp - h2_high)
            for hh in (h1_sp, h2_sp):
                if hh < 0.02: cost += 100000.0*(0.02-hh)
                if hh > 1.5: cost += 100000.0*(hh-1.5)
            if excess3 > 0.0:
                cost += 50000.0*excess3*h3
            if excess4 > 0.0:
                cost += 50000.0*excess4*h4
            if excess_v2 > 0.0:
                cost += 20000.0*excess_v2*v2
            if excess_v1 > 0.0:
                cost += 20000.0*excess_v1*v1
            return cost, h1_sp, h2_sp, h3, h4, v1, v2
        lo = max(0.02, sp_lo)
        hi = min(1.5, sp_hi)
        if hi < lo: lo, hi = hi, lo
        best = None
        best_cost = None
        num = int((hi-lo)/0.01) + 1
        for i in range(num):
            h1_sp = lo + i*0.01
            if h1_sp > hi: h1_sp = hi
            res = evaluate(h1_sp)
            if res is not None:
                if best_cost is None or res[0] < best_cost:
                    best_cost = res[0]; best = res
        if best is not None:
            c = best[1]
            for j in range(-20, 21):
                h1_sp = c + j*0.0005
                if h1_sp < lo or h1_sp > hi: continue
                res = evaluate(h1_sp)
                if res is not None and (best_cost is None or res[0] < best_cost):
                    best_cost = res[0]; best = res
        if best is None:
            h1_fb = min(max(active_setpoints["h1"], sp_lo), sp_hi)
            h2_fb = min(max(active_setpoints["h2"], sp_lo), sp_hi)
            return {"diagnosis":"no feasible setpoint; holding", "adjusted_setpoints":{"h1":h1_fb,"h2":h2_fb}}
        _, h1_sp, h2_sp, h3p, h4p, v1p, v2p = best
        h1_sp = min(max(h1_sp, sp_lo), sp_hi)
        h2_sp = min(max(h2_sp, sp_lo), sp_hi)
        diag = f"B={B_eff:.3f} D={D_eff:.3f} d1={d1_est:.2f} d2={d2_est:.2f} h3p={h3p:.2f} h4p={h4p:.2f} v1p={v1p:.2f} v2p={v2p:.2f}"
        return {"diagnosis": diag, "adjusted_setpoints":{"h1":h1_sp, "h2":h2_sp}}
    except Exception:
        return {"diagnosis":"fallback","adjusted_setpoints":{"h1":float(active_setpoints["h1"]),"h2":float(active_setpoints["h2"])}}