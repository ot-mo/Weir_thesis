def supervise(telemetry_window, active_setpoints, objectives):
    g = 9.81
    S2 = (2.0*g)**0.5
    a1=0.0035; a2=0.003; a3=0.002; a4=0.0025
    gam1=0.20; gam2=0.20
    k1n=0.00085; k2n=0.00095
    vmax=12.0
    W = telemetry_window
    n = len(W)
    last = W[n-1]
    t_now = last["time"]
    Q = objectives["production_target"] / 1000.0
    h2_lo = objectives["h2_band"][0]
    h2_hi = objectives["h2_band"][1]
    ulim = objectives["upper_level_limit"]
    lo_lim = objectives["setpoint_limits"][0]
    hi_lim = objectives["setpoint_limits"][1]

    def qh(h, a):
        if h <= 0.0: return 0.0
        return a * ((2.0*g*h)**0.5)
    def hq(q, a):
        if q <= 0.0: return 0.0
        r = q/(a*S2)
        return r*r

    d1_list = []
    d2_list = []
    times = []
    k1_cands = []
    k2_cands = []
    for i in range(1, n-1):
        h1 = W[i]["h1"]; h2 = W[i]["h2"]; h3 = W[i]["h3"]; h4 = W[i]["h4"]
        v1 = W[i]["v1"]; v2 = W[i]["v2"]
        dh1 = (W[i+1]["h1"] - W[i-1]["h1"]) / 2.0
        dh2 = (W[i+1]["h2"] - W[i-1]["h2"]) / 2.0
        dh3 = (W[i+1]["h3"] - W[i-1]["h3"]) / 2.0
        dh4 = (W[i+1]["h4"] - W[i-1]["h4"]) / 2.0
        if h4 > 0.0:
            A = (dh4 + a4*S2*(h4**0.5)) / (1.0 - gam1)
        else:
            A = 0.0
        if h3 > 0.0:
            B = (dh3 + a3*S2*(h3**0.5)) / (1.0 - gam2)
        else:
            B = 0.0
        if h1 > 0.0 and h3 > 0.0:
            d1 = dh1 + a1*S2*(h1**0.5) - a3*S2*(h3**0.5) - gam1*A
        else:
            d1 = 0.0
        if h2 > 0.0 and h4 > 0.0:
            d2 = dh2 + a2*S2*(h2**0.5) - a4*S2*(h4**0.5) - gam2*B
        else:
            d2 = 0.0
        d1_list.append(d1)
        d2_list.append(d2)
        times.append(W[i]["time"])
        if v1 > 5.0 and A > 0.0:
            k1_cands.append(A / v1)
        if v2 > 5.0 and B > 0.0:
            k2_cands.append(B / v2)

    def median(lst):
        if not lst: return None
        s = sorted(lst)
        m = len(s)
        if m % 2 == 1:
            return s[m//2]
        else:
            return 0.5*(s[m//2 - 1] + s[m//2])
    k1_eff = median(k1_cands)
    if k1_eff is None: k1_eff = k1n
    k2_eff = median(k2_cands)
    if k2_eff is None: k2_eff = k2n
    if k1_eff < 0.3*k1n: k1_eff = 0.3*k1n
    if k2_eff < 0.3*k2n: k2_eff = 0.3*k2n
    if k1_eff > 1.5*k1n: k1_eff = 1.5*k1n
    if k2_eff > 1.5*k2n: k2_eff = 1.5*k2n

    t_start = t_now - 300.0
    idx_win = [i for i,t in enumerate(times) if t >= t_start]
    if len(idx_win) < 10:
        idx_win = list(range(len(times)))
    d1_win = [d1_list[i] for i in idx_win]
    d2_win = [d2_list[i] for i in idx_win]

    def sign_changes(lst):
        sc = 0
        prev = 0
        for x in lst:
            s = 1 if x > 0.1 else (-1 if x < -0.1 else 0)
            if s != 0:
                if prev != 0 and s != prev:
                    sc += 1
                prev = s
        return sc
    sc1 = sign_changes(d1_win)
    sc2 = sign_changes(d2_win)
    amp1 = max([abs(x) for x in d1_win]) if d1_win else 0.0
    amp2 = max([abs(x) for x in d2_win]) if d2_win else 0.0
    osc1 = (sc1 >= 2 and amp1 > 0.3)
    osc2 = (sc2 >= 2 and amp2 > 0.3)

    if osc1:
        d1_min = min(d1_win) - 0.1
        d1_max = max(d1_win) + 0.1
    else:
        short = [d1_list[i] for i,t in enumerate(times) if t >= t_now - 60.0]
        if short:
            d1_min = min(short) - 0.05
            d1_max = max(short) + 0.05
        else:
            d1_min = d1_win[-1] - 0.05 if d1_win else -0.05
            d1_max = d1_win[-1] + 0.05 if d1_win else 0.05
    if osc2:
        d2_min = min(d2_win) - 0.1
        d2_max = max(d2_win) + 0.1
    else:
        short = [d2_list[i] for i,t in enumerate(times) if t >= t_now - 60.0]
        if short:
            d2_min = min(short) - 0.05
            d2_max = max(short) + 0.05
        else:
            d2_min = d2_win[-1] - 0.05 if d2_win else -0.05
            d2_max = d2_win[-1] + 0.05 if d2_win else 0.05

    B_lim_ulim = a3 * S2 * (ulim**0.5) / (1.0 - gam2)
    A_lim_ulim = a4 * S2 * (ulim**0.5) / (1.0 - gam1)
    B_lim_v = vmax * k2_eff
    A_lim_v = vmax * k1_eff

    h1_lo = max(0.02, lo_lim)
    h1_hi = min(1.5, hi_lim)
    q1_lo = qh(h1_lo, a1)
    q1_hi = qh(h1_hi, a1)
    q2_lo = qh(max(0.02, lo_lim), a2)
    q2_hi = qh(min(1.5, hi_lim), a2)
    q2_band_lo = qh(h2_lo, a2)
    q2_band_hi = qh(h2_hi, a2)

    cur_h1 = active_setpoints["h1"]
    cur_h2 = active_setpoints["h2"]
    cur_q1 = qh(cur_h1, a1)
    cur_q2 = qh(cur_h2, a2)

    best_cost = None
    best_q1 = cur_q1
    best_q2 = cur_q2

    q1_min = q1_lo
    q1_max = q1_hi
    q2_min = q2_lo
    q2_max = q2_hi
    step = 0.0002
    q1_vals = []
    v = q1_min
    while v <= q1_max + 1e-12:
        q1_vals.append(v)
        v += step
    if not q1_vals: q1_vals = [q1_min]
    q2_vals = []
    v = q2_min
    while v <= q2_max + 1e-12:
        q2_vals.append(v)
        v += step
    if not q2_vals: q2_vals = [q2_min]

    for q1 in q1_vals:
        for q2 in q2_vals:
            A_max = (4.0*q2 - q1 + d1_max - 4.0*d2_min) / 3.0
            B_max = (4.0*q1 - q2 - 4.0*d1_min + d2_max) / 3.0
            A_min = (4.0*q2 - q1 + d1_min - 4.0*d2_max) / 3.0
            B_min = (4.0*q1 - q2 - 4.0*d1_max + d2_min) / 3.0
            cost = 0.0
            if B_max > 0.0:
                h3p = (0.8*B_max / a3)**2 / (2.0*g)
                if h3p > ulim:
                    cost += 3000.0 * (h3p - ulim)
            if A_max > 0.0:
                h4p = (0.8*A_max / a4)**2 / (2.0*g)
                if h4p > ulim:
                    cost += 3000.0 * (h4p - ulim)
            v2p = B_max / k2_eff if k2_eff > 0 else 0.0
            v1p = A_max / k1_eff if k1_eff > 0 else 0.0
            if v2p > vmax:
                cost += 2000.0 * (v2p - vmax)
            if v1p > vmax:
                cost += 2000.0 * (v1p - vmax)
            if A_min < 0.0:
                cost += 2000.0 * (-A_min)
            if B_min < 0.0:
                cost += 2000.0 * (-B_min)
            h2p = hq(q2, a2) if q2 > 0 else 0.0
            if h2p < h2_lo:
                cost += 3000.0 * (h2_lo - h2p)
            if h2p > h2_hi:
                cost += 3000.0 * (h2p - h2_hi)
            h1p = hq(q1, a1) if q1 > 0 else 0.0
            if h1p < 0.02:
                cost += 3000.0 * (0.02 - h1p)
            if h1p > 1.5:
                cost += 3000.0 * (h1p - 1.5)
            if h1p < lo_lim:
                cost += 3000.0 * (lo_lim - h1p)
            if h1p > hi_lim:
                cost += 3000.0 * (h1p - hi_lim)
            if h2p < lo_lim:
                cost += 3000.0 * (lo_lim - h2p)
            if h2p > hi_lim:
                cost += 3000.0 * (h2p - hi_lim)
            q_err = abs(q1 + q2 - Q)
            cost += 10000.0 * q_err
            travel = abs(h1p - cur_h1) + abs(h2p - cur_h2)
            cost += 100.0 * travel
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_q1 = q1
                best_q2 = q2

    refine_step = 0.00005
    for _ in range(2):
        q1_c = best_q1
        q2_c = best_q2
        for dq1 in [-2*refine_step, -refine_step, 0.0, refine_step, 2*refine_step]:
            for dq2 in [-2*refine_step, -refine_step, 0.0, refine_step, 2*refine_step]:
                q1 = q1_c + dq1
                q2 = q2_c + dq2
                if q1 < q1_lo or q1 > q1_hi or q2 < q2_lo or q2 > q2_hi:
                    continue
                A_max = (4.0*q2 - q1 + d1_max - 4.0*d2_min) / 3.0
                B_max = (4.0*q1 - q2 - 4.0*d1_min + d2_max) / 3.0
                A_min = (4.0*q2 - q1 + d1_min - 4.0*d2_max) / 3.0
                B_min = (4.0*q1 - q2 - 4.0*d1_max + d2_min) / 3.0
                cost = 0.0
                if B_max > 0.0:
                    h3p = (0.8*B_max / a3)**2 / (2.0*g)
                    if h3p > ulim:
                        cost += 3000.0 * (h3p - ulim)
                if A_max > 0.0:
                    h4p = (0.8*A_max / a4)**2 / (2.0*g)
                    if h4p > ulim:
                        cost += 3000.0 * (h4p - ulim)
                v2p = B_max / k2_eff if k2_eff > 0 else 0.0
                v1p = A_max / k1_eff if k1_eff > 0 else 0.0
                if v2p > vmax:
                    cost += 2000.0 * (v2p - vmax)
                if v1p > vmax:
                    cost += 2000.0 * (v1p - vmax)
                if A_min < 0.0:
                    cost += 2000.0 * (-A_min)
                if B_min < 0.0:
                    cost += 2000.0 * (-B_min)
                h2p = hq(q2, a2) if q2 > 0 else 0.0
                if h2p < h2_lo:
                    cost += 3000.0 * (h2_lo - h2p)
                if h2p > h2_hi:
                    cost += 3000.0 * (h2p - h2_hi)
                h1p = hq(q1, a1) if q1 > 0 else 0.0
                if h1p < 0.02:
                    cost += 3000.0 * (0.02 - h1p)
                if h1p > 1.5:
                    cost += 3000.0 * (h1p - 1.5)
                if h1p < lo_lim:
                    cost += 3000.0 * (lo_lim - h1p)
                if h1p > hi_lim:
                    cost += 3000.0 * (h1p - hi_lim)
                if h2p < lo_lim:
                    cost += 3000.0 * (lo_lim - h2p)
                if h2p > hi_lim:
                    cost += 3000.0 * (h2p - hi_lim)
                q_err = abs(q1 + q2 - Q)
                cost += 10000.0 * q_err
                travel = abs(h1p - cur_h1) + abs(h2p - cur_h2)
                cost += 100.0 * travel
                if cost < best_cost:
                    best_cost = cost
                    best_q1 = q1
                    best_q2 = q2
        refine_step *= 0.5

    h1_des = hq(best_q1, a1)
    h2_des = hq(best_q2, a2)
    h1_des = min(hi_lim, max(lo_lim, h1_des))
    h2_des = min(hi_lim, max(lo_lim, h2_des))

    max_step = 0.08
    if h1_des - cur_h1 > max_step:
        h1_des = cur_h1 + max_step
    elif cur_h1 - h1_des > max_step:
        h1_des = cur_h1 - max_step
    if h2_des - cur_h2 > max_step:
        h2_des = cur_h2 + max_step
    elif cur_h2 - h2_des > max_step:
        h2_des = cur_h2 - max_step

    if abs(h1_des - cur_h1) < 0.005 and abs(h2_des - cur_h2) < 0.005:
        h1_des = cur_h1
        h2_des = cur_h2

    return {
        "diagnosis": "robust model-based supervisor: windowed disturbance bounds, worst-case feasibility search with production and travel trade-off",
        "adjusted_setpoints": {"h1": h1_des, "h2": h2_des},
    }
