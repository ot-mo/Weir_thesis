def supervise(telemetry_window, active_setpoints, objectives):
    a1=0.0035
    a2=0.003
    a3=0.002
    a4=0.0025
    k1=0.00085
    k2=0.00095
    g=9.81
    c=math.sqrt(2.0*g)
    a1c=1000.0*a1*c
    a2c=1000.0*a2*c
    a3c=1000.0*a3*c
    a4c=1000.0*a4*c
    try:
        h1a=float(active_setpoints['h1'])
        h2a=float(active_setpoints['h2'])
    except Exception:
        h1a=0.30
        h2a=0.35
    fallback={'diagnosis':'hold setpoints','adjusted_setpoints':{'h1':h1a,'h2':h2a}}
    try:
        Q_t=float(objectives['production_target'])
        band=objectives['h2_band']
        h2lo=float(band[0])
        h2hi=float(band[1])
        ulim=float(objectives['upper_level_limit'])
        lim=objectives['setpoint_limits']
        splo=float(lim[0])
        sphi=float(lim[1])
        n=len(telemetry_window)
        if n<5:
            return fallback
        m=20
        if n<m:
            m=n
        tail=telemetry_window[n-m:]
        def fit(key):
            vals=[]
            for row in tail:
                vals.append(float(row[key]))
            mm=len(vals)
            if mm<2:
                return vals[0],0.0
            mt=(mm-1)*0.5
            num=0.0
            den=0.0
            s=0.0
            for i in range(mm):
                d=i-mt
                num+=d*vals[i]
                den+=d*d
                s+=vals[i]
            sl=num/den if den>0.0 else 0.0
            mean=s/mm
            return mean+sl*(mm-1-mt), sl
        h1,sh1=fit('h1')
        h2,sh2=fit('h2')
        h3,sh3=fit('h3')
        h4,sh4=fit('h4')
        v1,sv1=fit('v1')
        v2,sv2=fit('v2')
    except Exception:
        return fallback
    if h1<0.0: h1=0.0
    if h2<0.0: h2=0.0
    if h3<0.0: h3=0.0
    if h4<0.0: h4=0.0
    if v1<0.0: v1=0.0
    if v2<0.0: v2=0.0
    Q1_meas=a1c*math.sqrt(h1)
    Q2_meas=a2c*math.sqrt(h2)
    X_flow=a3c*math.sqrt(h3)
    Y_flow=a4c*math.sqrt(h4)
    sh1L=1000.0*sh1
    sh2L=1000.0*sh2
    sh3L=1000.0*sh3
    sh4L=1000.0*sh4
    infl3=X_flow+sh3L
    infl4=Y_flow+sh4L
    if infl3<0.0: infl3=0.0
    if infl4<0.0: infl4=0.0
    d1=sh1L+Q1_meas-X_flow-0.25*infl4
    d2=sh2L+Q2_meas-Y_flow-0.25*infl3
    if v1>0.1:
        k1_eff=(1.25*infl4)/v1
    else:
        k1_eff=0.85
    if v2>0.1:
        k2_eff=(1.25*infl3)/v2
    else:
        k2_eff=0.95
    if k1_eff<0.01: k1_eff=0.01
    if k2_eff<0.01: k2_eff=0.01
    vmax_hard=12.0
    vmax_soft=11.7
    vmin_hard=1.0
    vmin_soft=1.2
    h1_safe_lo=0.02
    h1_safe_hi=1.5
    if splo>h1_safe_lo: h1_safe_lo=splo
    if sphi<h1_safe_hi: h1_safe_hi=sphi
    h2_safe_lo=0.02
    h2_safe_hi=1.5
    if splo>h2_safe_lo: h2_safe_lo=splo
    if sphi<h2_safe_hi: h2_safe_hi=sphi
    Q1_min_safe=a1c*math.sqrt(h1_safe_lo)
    Q1_max_safe=a1c*math.sqrt(h1_safe_hi)
    Q2_min_safe=a2c*math.sqrt(h2_safe_lo)
    Q2_max_safe=a2c*math.sqrt(h2_safe_hi)
    Q1_min=max(Q1_min_safe, Q_t-Q2_max_safe)
    Q1_max=min(Q1_max_safe, Q_t-Q2_min_safe)
    if Q1_min>Q1_max:
        return fallback
    step=0.005
    if Q1_max-Q1_min>10.0:
        step=0.01
    n_steps=int((Q1_max-Q1_min)/step)+1
    if n_steps>2000:
        n_steps=2000
        if n_steps>1:
            step=(Q1_max-Q1_min)/(n_steps-1)
        else:
            step=0.0
    best_level=99
    best_travel=1e9
    best_overflow=0.0
    best_h1=h1a
    best_h2=h2a
    for i in range(n_steps):
        Q1=Q1_min+i*step
        if Q1>Q1_max: Q1=Q1_max
        Q2=Q_t-Q1
        if Q1<0.0 or Q2<0.0:
            continue
        h1_c=(Q1/a1c)**2
        h2_c=(Q2/a2c)**2
        if h1_c<h1_safe_lo or h1_c>h1_safe_hi:
            continue
        if h2_c<h2_safe_lo or h2_c>h2_safe_hi:
            continue
        A=Q1-d1
        B=Q2-d2
        X_req=(4.0/15.0)*(4.0*A-B)
        Y_req=(4.0/15.0)*(4.0*B-A)
        if X_req<0.0: X_req=0.0
        if Y_req<0.0: Y_req=0.0
        h3_pred=(X_req/a3c)**2
        h4_pred=(Y_req/a4c)**2
        v1_req=(1.25*Y_req)/k1_eff
        v2_req=(1.25*X_req)/k2_eff
        travel=abs(h1_c-h1a)+abs(h2_c-h2a)
        level=0
        overflow=0.0
        if h3_pred>ulim-0.02 or h4_pred>ulim-0.02:
            level=1
        if v1_req>vmax_soft or v2_req>vmax_soft:
            level=1
        if v1_req<vmin_soft or v2_req<vmin_soft:
            level=1
        if h2_c<h2lo+0.005 or h2_c>h2hi-0.005:
            level=1
        if level==0:
            pass
        else:
            level=1
            hard=False
            if h3_pred>ulim or h4_pred>ulim:
                hard=True
                overflow+=max(0.0,h3_pred-ulim)+max(0.0,h4_pred-ulim)
            if v1_req>vmax_hard or v2_req>vmax_hard:
                hard=True
                overflow+=max(0.0,v1_req-vmax_hard)+max(0.0,v2_req-vmax_hard)
            if v1_req<vmin_hard or v2_req<vmin_hard:
                hard=True
                overflow+=max(0.0,vmin_hard-v1_req)+max(0.0,vmin_hard-v2_req)
            if h2_c<h2lo or h2_c>h2hi:
                hard=True
                overflow+=max(0.0,h2lo-h2_c)+max(0.0,h2_c-h2hi)
            if hard:
                level=2
            else:
                level=1
        if level<best_level:
            best_level=level
            best_travel=travel
            best_overflow=overflow
            best_h1=h1_c
            best_h2=h2_c
        elif level==best_level:
            if travel<best_travel-1e-9:
                best_travel=travel
                best_overflow=overflow
                best_h1=h1_c
                best_h2=h2_c
            elif abs(travel-best_travel)<1e-9:
                if overflow<best_overflow-1e-9:
                    best_overflow=overflow
                    best_h1=h1_c
                    best_h2=h2_c
    if best_level==99:
        return fallback
    if best_h1<h1_safe_lo: best_h1=h1_safe_lo
    if best_h1>h1_safe_hi: best_h1=h1_safe_hi
    if best_h2<h2_safe_lo: best_h2=h2_safe_lo
    if best_h2>h2_safe_hi: best_h2=h2_safe_hi
    Q1_f=a1c*math.sqrt(best_h1)
    Q2_f=a2c*math.sqrt(best_h2)
    A=Q1_f-d1
    B=Q2_f-d2
    X_req=(4.0/15.0)*(4.0*A-B)
    Y_req=(4.0/15.0)*(4.0*B-A)
    if X_req<0.0: X_req=0.0
    if Y_req<0.0: Y_req=0.0
    h3p=(X_req/a3c)**2
    h4p=(Y_req/a4c)**2
    v1r=(1.25*Y_req)/k1_eff
    v2r=(1.25*X_req)/k2_eff
    diag='lvl=%d trav=%.3f h1=%.3f h2=%.3f v1r=%.1f v2r=%.1f h3p=%.2f h4p=%.2f d1=%.2f d2=%.2f' % (best_level,best_travel,best_h1,best_h2,v1r,v2r,h3p,h4p,d1,d2)
    return {'diagnosis':diag,'adjusted_setpoints':{'h1':best_h1,'h2':best_h2}}