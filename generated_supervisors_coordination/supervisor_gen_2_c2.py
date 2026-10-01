def supervise(telemetry_window, active_setpoints, objectives):
    sq2g = 4.42944691807002
    a1 = 0.0035
    a2 = 0.003
    a3 = 0.002
    a4 = 0.0025
    k1 = 0.00085
    k2 = 0.00095
    gam1 = 0.20
    gam2 = 0.20
    c1 = gam1 / (1.0 - gam1)
    c2 = gam2 / (1.0 - gam2)
    den = 1.0 - c1 * c2

    n = len(telemetry_window)
    if n < 10:
        return {"diagnosis": "too few samples, holding",
                "adjusted_setpoints": {"h1": float(active_setpoints["h1"]),
                                       "h2": float(active_setpoints["h2"])}}

    N = n
    win = telemetry_window[-N:]

    sum_d1 = 0.0
    sum_d2 = 0.0
    count = 0
    sum_k1 = 0.0
    sum_k2 = 0.0
    count_k1 = 0
    count_k2 = 0
    for i in range(1, N):
        r_prev = win[i - 1]
        r_cur = win[i]
        dt = r_cur["time"] - r_prev["time"]
        if dt <= 0:
            continue
        h1 = r_cur["h1"]
        h2 = r_cur["h2"]
        h3 = r_cur["h3"]
        h4 = r_cur["h4"]
        v1 = r_cur["v1"]
        v2 = r_cur["v2"]
        dh1 = (r_cur["h1"] - r_prev["h1"]) / dt
        dh2 = (r_cur["h2"] - r_prev["h2"]) / dt
        dh3 = (r_cur["h3"] - r_prev["h3"]) / dt
        dh4 = (r_cur["h4"] - r_prev["h4"]) / dt
        f1 = a1 * sq2g * math.sqrt(h1) if h1 > 0 else 0.0
        f2 = a2 * sq2g * math.sqrt(h2) if h2 > 0 else 0.0
        f3 = a3 * sq2g * math.sqrt(h3) if h3 > 0 else 0.0
        f4 = a4 * sq2g * math.sqrt(h4) if h4 > 0 else 0.0
        d1_i = dh1 + f1 - f3 - gam1 * k1 * v1
        d2_i = dh2 + f2 - f4 - gam2 * k2 * v2
        sum_d1 += d1_i
        sum_d2 += d2_i
        count += 1
        if v1 > 0.1:
            k1_est = (dh4 + f4) / ((1.0 - gam1) * v1)
            sum_k1 += k1_est
            count_k1 += 1
        if v2 > 0.1:
            k2_est = (dh3 + f3) / ((1.0 - gam2) * v2)
            sum_k2 += k2_est
            count_k2 += 1

    if count > 0:
        d1 = sum_d1 / count
        d2 = sum_d2 / count
    else:
        d1 = 0.0
        d2 = 0.0
    if count_k1 > 0:
        k1_eff = sum_k1 / count_k1
    else:
        k1_eff = k1
    if count_k2 > 0:
        k2_eff = sum_k2 / count_k2
    else:
        k2_eff = k2
    k1_eff = max(0.3 * k1, min(2.0 * k1, k1_eff))
    k2_eff = max(0.3 * k2, min(2.0 * k2, k2_eff))

    Q_target_Ls = objectives["production_target"]
    if Q_target_Ls <= 0:
        Q_target_Ls = 16.3529
    Q_target = Q_target_Ls / 1000.0

    hlim = objectives["upper_level_limit"]
    h3t = hlim - 0.02
    if h3t < 0.10:
        h3t = 0.10
    h4t = h3t

    sp_lo, sp_hi = objectives["setpoint_limits"]
    h2lo, h2hi = objectives["h2_band"]
    h1_safe_lo = 0.02
    h1_safe_hi = 1.5
    h2_safe_lo = 0.02
    h2_safe_hi = 1.5

    h1_min = max(sp_lo, h1_safe_lo)
    h1_max = min(sp_hi, h1_safe_hi)
    h2_min = max(h2lo, h2_safe_lo)
    h2_max = min(h2hi, h2_safe_hi)

    f3max = a3 * sq2g * math.sqrt(h3t)
    f4max = a4 * sq2g * math.sqrt(h4t)

    f3_min_v2 = 1.0 * (1.0 - gam2) * k2_eff
    f3_max_v2 = 12.0 * (1.0 - gam2) * k2_eff
    f4_min_v1 = 1.0 * (1.0 - gam1) * k1_eff
    f4_max_v1 = 12.0 * (1.0 - gam1) * k1_eff

    f3_min = max(0.0, f3_min_v2)
    f3_max = min(f3max, f3_max_v2)
    f4_min = max(0.0, f4_min_v1)
    f4_max = min(f4max, f4_max_v1)

    n5 = min(5, N)
    s_Q5 = 0.0
    for j in range(N - n5, N):
        s_Q5 += win[j]["production"]
    Q_last_avg = s_Q5 / n5

    Kq = 0.1
    err = Q_target_Ls - Q_last_avg
    if abs(err) > 0.05:
        Q_des_Ls = Q_target_Ls + Kq * err
        Q_des_Ls = max(0.9 * Q_target_Ls, min(1.1 * Q_target_Ls, Q_des_Ls))
        Q_des = Q_des_Ls / 1000.0
    else:
        Q_des = Q_target

    def get_feasible(Q, h2_min_val, h2_max_val):
        f1_min_h1 = a1 * sq2g * math.sqrt(h1_min)
        f1_max_h1 = a1 * sq2g * math.sqrt(h1_max)
        f2_min = a2 * sq2g * math.sqrt(h2_min_val)
        f2_max = a2 * sq2g * math.sqrt(h2_max_val)
        A3 = (1.0 + c1) / den
        B3 = (-d1 - c1 * Q + c1 * d2) / den
        A4 = -(1.0 + c2 * A3)
        B4 = Q - d2 - c2 * B3
        lo = 0.0
        hi = Q
        lo = max(lo, f1_min_h1)
        hi = min(hi, f1_max_h1)
        lo = max(lo, Q - f2_max)
        hi = min(hi, Q - f2_min)
        if A3 > 0:
            lo = max(lo, (f3_min - B3) / A3)
            hi = min(hi, (f3_max - B3) / A3)
        if A4 < 0:
            lo = max(lo, (f4_max - B4) / A4)
            hi = min(hi, (f4_min - B4) / A4)
        return lo, hi

    attempts = [
        (Q_des, h2_min, h2_max),
        (Q_des, h2_safe_lo, h2_safe_hi),
        (Q_target, h2_min, h2_max),
        (Q_target, h2_safe_lo, h2_safe_hi)
    ]
    feasible = False
    for Q_try, h2min_try, h2max_try in attempts:
        lo, hi = get_feasible(Q_try, h2min_try, h2max_try)
        if lo <= hi:
            feasible = True
            Q_use = Q_try
            break

    if feasible:
        h1a = active_setpoints["h1"]
        h2a = active_setpoints["h2"]
        candidates = [lo, hi]
        F1_h1 = a1 * sq2g * math.sqrt(h1a) if h1a > 0 else 0.0
        if lo <= F1_h1 <= hi:
            candidates.append(F1_h1)
        F1_h2 = Q_use - a2 * sq2g * math.sqrt(h2a) if h2a > 0 else 0.0
        if lo <= F1_h2 <= hi:
            candidates.append(F1_h2)
        best_F1 = lo
        best_travel = 1e9
        for F1 in candidates:
            F2 = Q_use - F1
            h1_c = (F1 / (a1 * sq2g)) ** 2
            h2_c = (F2 / (a2 * sq2g)) ** 2
            travel = abs(h1_c - h1a) + abs(h2_c - h2a)
            if travel < best_travel:
                best_travel = travel
                best_F1 = F1
        F1 = best_F1
        Q_final = Q_use
    else:
        best_F1 = Q_target * 0.5
        best_cost = 1e9
        steps = 200
        for i in range(steps + 1):
            F1 = Q_target * i / steps
            F2 = Q_target - F1
            if F1 < 0 or F2 < 0:
                continue
            h1_c = (F1 / (a1 * sq2g)) ** 2
            h2_c = (F2 / (a2 * sq2g)) ** 2
            f3_c = (F1 - d1 - c1 * (F2 - d2)) / den
            f4_c = F2 - d2 - c2 * f3_c
            if f3_c < 0:
                f3_c = 0.0
            if f4_c < 0:
                f4_c = 0.0
            h3_c = (f3_c / (a3 * sq2g)) ** 2 if f3_c > 0 else 0.0
            h4_c = (f4_c / (a4 * sq2g)) ** 2 if f4_c > 0 else 0.0
            v1_c = f4_c / ((1.0 - gam1) * k1_eff) if k1_eff > 0 else 0.0
            v2_c = f3_c / ((1.0 - gam2) * k2_eff) if k2_eff > 0 else 0.0
            cost = 0.0
            if h1_c < h1_safe_lo or h1_c > h1_safe_hi:
                cost += 10000
            if h2_c < h2_safe_lo or h2_c > h2_safe_hi:
                cost += 10000
            if h3_c > hlim:
                cost += 5000 * (h3_c - hlim)
            if h4_c > hlim:
                cost += 5000 * (h4_c - hlim)
            if h2_c > h2hi:
                cost += 1000 * (h2_c - h2hi)
            if h2_c < h2lo:
                cost += 1000 * (h2lo - h2_c)
            if v1_c > 12.0:
                cost += 1000 * (v1_c - 12.0)
            if v1_c < 1.0:
                cost += 1000 * (1.0 - v1_c)
            if v2_c > 12.0:
                cost += 1000 * (v2_c - 12.0)
            if v2_c < 1.0:
                cost += 1000 * (1.0 - v2_c)
            if h1_c < sp_lo or h1_c > sp_hi:
                cost += 1000
            if h2_c < sp_lo or h2_c > sp_hi:
                cost += 1000
            travel = abs(h1_c - active_setpoints["h1"]) + abs(h2_c - active_setpoints["h2"])
            cost += 100.0 * travel
            if cost < best_cost:
                best_cost = cost
                best_F1 = F1
        F1 = best_F1
        Q_final = Q_target

    F2 = Q_final - F1
    if F2 < 0:
        F2 = 0.0
    h1_sp = (F1 / (a1 * sq2g)) ** 2
    h2_sp = (F2 / (a2 * sq2g)) ** 2

    h1_sp = max(sp_lo, min(sp_hi, h1_sp))
    h2_sp = max(sp_lo, min(sp_hi, h2_sp))
    h1_sp = max(h1_safe_lo, min(h1_safe_hi, h1_sp))
    h2_sp = max(h2_safe_lo, min(h2_safe_hi, h2_sp))

    if abs(h1_sp - active_setpoints["h1"]) < 0.001 and abs(h2_sp - active_setpoints["h2"]) < 0.001:
        h1_sp = active_setpoints["h1"]
        h2_sp = active_setpoints["h2"]

    diag = ("Q_des=" + str(round(Q_des * 1000, 2)) +
            " d1=" + str(round(d1, 5)) + " d2=" + str(round(d2, 5)) +
            " k1e=" + str(round(k1_eff, 6)) + " k2e=" + str(round(k2_eff, 6)) +
            " -> h1=" + str(round(h1_sp, 3)) + " h2=" + str(round(h2_sp, 3)))
    return {"diagnosis": diag,
            "adjusted_setpoints": {"h1": float(h1_sp), "h2": float(h2_sp)}}