def supervise(telemetry_window, active_setpoints, objectives):
    a1 = 0.0035
    a2 = 0.0030
    a3 = 0.0020
    a4 = 0.0025
    g = 9.81
    k1 = 0.00085
    k2 = 0.00095
    gam1 = 0.20
    gam2 = 0.20
    Acoef = gam1 * k1
    Bcoef = (1.0 - gam2) * k2
    Ccoef = (1.0 - gam1) * k1
    Dcoef = gam2 * k2
    det = Acoef * Dcoef - Bcoef * Ccoef
    if det > -1.0e-12 and det < 1.0e-12:
        det = -1.0e-12
    Ka = Acoef + Ccoef
    Kb = Bcoef + Dcoef
    sq2g = math.sqrt(2.0 * g)
    qa1 = a1 * sq2g
    qa2 = a2 * sq2g

    Qtar = objectives["production_target"] * 0.001
    slo, shi = objectives["setpoint_limits"]
    h2lo, h2hi = objectives["h2_band"]
    ulim = objectives["upper_level_limit"]
    h3lim = ulim - 0.03
    h4lim = ulim - 0.03
    if h3lim < 0.05:
        h3lim = 0.05
    if h4lim < 0.05:
        h4lim = 0.05
    sp1 = active_setpoints["h1"]
    sp2 = active_setpoints["h2"]

    w = telemetry_window
    nw = len(w)
    last = w[nw - 1]
    h1 = last["h1"]
    h2 = last["h2"]
    h3 = last["h3"]
    h4 = last["h4"]
    v1 = last["v1"]
    v2 = last["v2"]

    dh1 = 0.0
    dh2 = 0.0
    dh3 = 0.0
    dh4 = 0.0
    n = 8
    if nw > n:
        o = w[nw - 1 - n]
        dt = last["time"] - o["time"]
        if dt <= 0.0:
            dt = 1.0
        dh1 = (h1 - o["h1"]) / dt
        dh2 = (h2 - o["h2"]) / dt
        dh3 = (h3 - o["h3"]) / dt
        dh4 = (h4 - o["h4"]) / dt
    limd = 0.01
    if dh1 > limd:
        dh1 = limd
    if dh1 < -limd:
        dh1 = -limd
    if dh2 > limd:
        dh2 = limd
    if dh2 < -limd:
        dh2 = -limd
    if dh3 > limd:
        dh3 = limd
    if dh3 < -limd:
        dh3 = -limd
    if dh4 > limd:
        dh4 = limd
    if dh4 < -limd:
        dh4 = -limd

    if h1 < 0.0:
        h1 = 0.0
    if h2 < 0.0:
        h2 = 0.0
    if h3 < 0.0:
        h3 = 0.0
    if h4 < 0.0:
        h4 = 0.0

    Q1ss = qa1 * math.sqrt(h1) + dh1 + dh3
    Q2ss = qa2 * math.sqrt(h2) + dh2 + dh4
    d1e = Q1ss - (Acoef * v1 + Bcoef * v2)
    d2e = Q2ss - (Ccoef * v1 + Dcoef * v2)

    s3 = math.sqrt(h3) + dh3 / (a3 * sq2g)
    if s3 < 0.0001:
        s3 = 0.0001
    h3eq = s3 * s3
    s4 = math.sqrt(h4) + dh4 / (a4 * sq2g)
    if s4 < 0.0001:
        s4 = 0.0001
    h4eq = s4 * s4
    if h3eq > 1.5:
        h3eq = 1.5
    if h4eq > 1.5:
        h4eq = 1.5

    ve1 = v1
    if ve1 < 0.2:
        ve1 = 0.2
    ve2 = v2
    if ve2 < 0.2:
        ve2 = 0.2

    Q1sp = 0.0
    if sp1 > 0.0:
        Q1sp = qa1 * math.sqrt(sp1)
    Q2sp = 0.0
    if sp2 > 0.0:
        Q2sp = qa2 * math.sqrt(sp2)
    v2ref = (Acoef * (Q2sp - d2e) - Ccoef * (Q1sp - d1e)) / det

    besth1 = sp1
    besth2 = sp2
    bestcost = None
    i = 0
    while i <= 1100:
        v2t = 1.0 + 0.01 * i
        i = i + 1
        v1t = (Qtar - d1e - d2e - Kb * v2t) / Ka
        Q1t = Acoef * v1t + Bcoef * v2t + d1e
        Q2t = Qtar - Q1t
        if Q1t <= 1.0e-7:
            continue
        if Q2t <= 1.0e-7:
            continue
        h1t = (Q1t / qa1) * (Q1t / qa1)
        h2t = (Q2t / qa2) * (Q2t / qa2)
        r3 = v2t / ve2
        h3t = h3eq * r3 * r3
        r4 = v1t / ve1
        h4t = h4eq * r4 * r4
        pen = 0.0
        if h3t > h3lim:
            pen = pen + (h3t - h3lim)
        if h4t > h4lim:
            pen = pen + (h4t - h4lim)
        if h2t > h2hi:
            pen = pen + (h2t - h2hi)
        if h2t < h2lo:
            pen = pen + (h2lo - h2t)
        if h1t > 1.5:
            pen = pen + (h1t - 1.5)
        if h1t < 0.02:
            pen = pen + (0.02 - h1t)
        if h1t > shi:
            pen = pen + (h1t - shi)
        if h1t < slo:
            pen = pen + (slo - h1t)
        if h2t > shi:
            pen = pen + (h2t - shi)
        if h2t < slo:
            pen = pen + (slo - h2t)
        if v1t > 12.0:
            pen = pen + (v1t - 12.0)
        if v1t < 1.0:
            pen = pen + (1.0 - v1t)
        if v2t > 12.0:
            pen = pen + (v2t - 12.0)
        if v2t < 1.0:
            pen = pen + (1.0 - v2t)
        tr = abs(h1t - sp1) + abs(h2t - sp2)
        cost = tr + 1000.0 * pen + 1.0e-6 * abs(v2t - v2ref)
        if bestcost is None or cost < bestcost:
            bestcost = cost
            besth1 = h1t
            besth2 = h2t

    if abs(besth1 - sp1) < 0.002 and abs(besth2 - sp2) < 0.002:
        besth1 = sp1
        besth2 = sp2
    if besth1 > shi:
        besth1 = shi
    if besth1 < slo:
        besth1 = slo
    if besth2 > shi:
        besth2 = shi
    if besth2 < slo:
        besth2 = slo

    diag = "steady-state supervisor: Q=" + str(round(Qtar * 1000.0, 2)) + " L/s, sp=(" + str(round(besth1, 3)) + "," + str(round(besth2, 3)) + ")"
    return {"diagnosis": diag, "adjusted_setpoints": {"h1": besth1, "h2": besth2}}