def supervise(telemetry_window, active_setpoints, objectives):
    a1=0.0035; a2=0.003; a3=0.002; a4=0.0025
    g=9.81
    gamma1=0.20; gamma2=0.20
    K1n=0.85; K2n=0.95

    Q_t = objectives["production_target"]
    h2_low, h2_high = objectives["h2_band"]
    upper_lim = objectives["upper_level_limit"]
    sp_lo, sp_hi = objectives["setpoint_limits"]

    n = len(telemetry_window)
    if n == 0:
        return {"diagnosis":"empty telemetry; holding nominal",
                "adjusted_setpoints":{"h1":min(max(0.30,sp_lo),sp_hi),
                                      "h2":min(max(0.35,sp_lo),sp_hi)}}

    # average the last up to 10 samples for smoother estimates
    k = 10 if n >= 10 else n
    rec = telemetry_window[n-k:]
    m = len(rec)
    sh1=sh2=sh3=sh4=sv1=sv2=0.0
    for s in rec:
        sh1+=s["h1"]; sh2+=s["h2"]; sh3+=s["h3"]; sh4+=s["h4"]; sv1+=s["v1"]; sv2+=s["v2"]
    h1c=sh1/m; h2c=sh2/m; h3c=sh3/m; h4c=sh4/m; v1c=sv1/m; v2c=sv2/m

    def qv(h, a):
        if h <= 0.0: return 0.0
        return 1000.0*a*math.sqrt(2.0*g*h)
    def hq(q, a):
        if q <= 0.0: return 0.0
        return (q/(1000.0*a))**2/(2.0*g)

    q1c=qv(h1c,a1); q2c=qv(h2c,a2); q3c=qv(h3c,a3); q4c=qv(h4c,a4)

    B_est = q4c/v1c if v1c > 2.0 else (1.0-gamma1)*K1n
    D_est = q3c/v2c if v2c > 2.0 else (1.0-gamma2)*K2n
    if B_est < 0.1: B_est = 0.1
    if B_est > 2.0: B_est = 2.0
    if D_est < 0.1: D_est = 0.1
    if D_est > 2.0: D_est = 2.0

    alpha = gamma1/(1.0-gamma1)
    beta  = gamma2/(1.0-gamma2)
    A_est = alpha*B_est
    C_est = beta*D_est

    d1_est = q1c - q3c - A_est*v1c
    d2_est = q2c - q4c - C_est*v2c

    det = 1.0 - alpha*beta
    if abs(det) < 1e-6:
        h1_fb = min(max(active_setpoints["h1"], sp_lo), sp_hi)
        h2_fb = min(max(active_setpoints["h2"], sp_lo), sp_hi)
        return {"diagnosis":"singular split; holding active setpoints",
                "adjusted_setpoints":{"h1":h1_fb,"h2":h2_fb}}
    invdet = 1.0/det

    m_up = 0.02
    mv = 0.5
    v_lo = 1.0; v_hi = 12.0

    def evaluate(h1_sp, q_t):
        if h1_sp <= 0.005 or h1_sp >= 1.6:
            return None
        q1 = qv(h1_sp, a1)
        q2 = q_t - q1
        if q2 <= 0.05:
            return None
        h2_sp = hq(q2, a2)
        rhs1 = q1 - d1_est
        rhs2 = q2 - d2_est
        q3 = (rhs1 - alpha*rhs2)*invdet
        q4 = (rhs2 - beta*rhs1)*invdet
        if q3 < -0.05 or q4 < -0.05:
            return None
        if q3 < 0.0: q3 = 0.0
        if q4 < 0.0: q4 = 0.0
        h3 = hq(q3, a3); h4 = hq(q4, a4)
        v1 = q4/B_est if B_est > 0.0 else 0.0
        v2 = q3/D_est if D_est > 0.0 else 0.0

        travel = abs(h1_sp - active_setpoints["h1"]) + abs(h2_sp - active_setpoints["h2"])
        cost = travel
        cost += 20.0*abs(q_t - Q_t)

        # upper-level penalties (very steep past limit, soft margin before)
        if h3 > upper_lim:
            cost += 20000.0*(h3 - upper_lim + m_up)
        elif h3 > upper_lim - m_up:
            cost += 500.0*(h3 - (upper_lim - m_up))
        if h4 > upper_lim:
            cost += 20000.0*(h4 - upper_lim + m_up)
        elif h4 > upper_lim - m_up:
            cost += 500.0*(h4 - (upper_lim - m_up))

        # h2 band penalties
        if h2_sp < h2_low:
            cost += 200.0*(h2_low - h2_sp)
        elif h2_sp < h2_low + 0.01:
            cost += 20.0*(h2_low + 0.01 - h2_sp)
        if h2_sp > h2_high:
            cost += 200.0*(h2_sp - h2_high)
        elif h2_sp > h2_high - 0.01:
            cost += 20.0*(h2_sp - (h2_high - 0.01))

        # pump saturation penalties
        if v1 > v_hi:
            cost += 500.0*(v1 - v_hi)
        elif v1 > v_hi - mv:
            cost += 30.0*(v1 - (v_hi - mv))
        if v1 < v_lo:
            cost += 500.0*(v_lo - v1)
        elif v1 < v_lo + mv:
            cost += 30.0*(v_lo + mv - v1)
        if v2 > v_hi:
            cost += 500.0*(v2 - v_hi)
        elif v2 > v_hi - mv:
            cost += 30.0*(v2 - (v_hi - mv))
        if v2 < v_lo:
            cost += 500.0*(v_lo - v2)
        elif v2 < v_lo + mv:
            cost += 30.0*(v_lo + mv - v2)

        # safety limits on h1,h2
        if h1_sp < 0.02: cost += 10000.0*(0.02 - h1_sp)
        if h1_sp > 1.5: cost += 10000.0*(h1_sp - 1.5)
        if h2_sp < 0.02: cost += 10000.0*(0.02 - h2_sp)
        if h2_sp > 1.5: cost += 10000.0*(h2_sp - 1.5)

        return (cost, h1_sp, h2_sp, h3, h4, v1, v2)

    best = None; best_cost = None
    nsteps = 149
    for i in range(nsteps+1):
        h1_sp = 0.02 + i*0.01
        r = evaluate(h1_sp, Q_t)
        if r is not None and (best_cost is None or r[0] < best_cost):
            best_cost = r[0]; best = r

    if best is not None:
        h1_try = best[1]
        for i in range(-12, 13):
            h1_sp = h1_try + i*0.001
            r = evaluate(h1_sp, Q_t)
            if r is not None and r[0] < best_cost:
                best_cost = r[0]; best = r

    def hard_viol(r):
        if r[3] > upper_lim + 1e-9: return True
        if r[4] > upper_lim + 1e-9: return True
        if r[5] > v_hi + 1e-9: return True
        if r[6] > v_hi + 1e-9: return True
        if r[5] < v_lo - 1e-9: return True
        if r[6] < v_lo - 1e-9: return True
        return False

    # fallback: relax production slightly if the exact-Q solution cannot be made compliant
    if best is None or hard_viol(best):
        for f in (0.98, 0.96, 0.94, 0.92, 0.90, 0.88, 0.86):
            q_t = Q_t*f
            for i in range(nsteps+1):
                h1_sp = 0.02 + i*0.01
                r = evaluate(h1_sp, q_t)
                if r is not None and (best_cost is None or r[0] < best_cost):
                    best_cost = r[0]; best = r
            if best is not None and not hard_viol(best):
                break

    if best is None:
        h1_fb = min(max(active_setpoints["h1"], sp_lo), sp_hi)
        h2_fb = min(max(active_setpoints["h2"], sp_lo), sp_hi)
        return {"diagnosis":"no feasible setpoint found; holding active setpoints",
                "adjusted_setpoints":{"h1":h1_fb,"h2":h2_fb}}

    _, h1_sp, h2_sp, h3p, h4p, v1p, v2p = best
    h1_sp = min(max(h1_sp, sp_lo), sp_hi)
    h2_sp = min(max(h2_sp, sp_lo), sp_hi)
    diag = "model-based: B={:.3f} D={:.3f} d1={:.2f} d2={:.2f} pred h3={:.3f} h4={:.3f} v1={:.2f} v2={:.2f}".format(B_est, D_est, d1_est, d2_est, h3p, h4p, v1p, v2p)
    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"h1": h1_sp, "h2": h2_sp}
    }
