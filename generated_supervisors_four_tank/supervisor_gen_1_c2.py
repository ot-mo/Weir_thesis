def supervise(telemetry_window, active_setpoints, nominal_targets):
    n = len(telemetry_window)
    k = 10
    if n < k:
        k = n
    lo = n - k

    def loop_mean(tank):
        if k <= 0:
            return 0.0
        s = 0.0
        for i in range(lo, n):
            s += telemetry_window[i][tank]["pump_effort"]
        return s / k

    # Each loop's own output voltage, over the 10 s since the previous call.
    # tank1.pump_effort is pump 2 (feeds tank3 -> tank1); tank2.pump_effort is
    # pump 1 (feeds tank4 -> tank2).
    m1 = loop_mean("tank1")
    m2 = loop_mean("tank2")

    # Pumps saturate at 12 V. In the fault-free reference episode the tank1
    # loop never exceeds 10.59 V and the tank2 loop never exceeds 9.26 V, over
    # BOTH the start-up transient and settled operation. An outlet leak makes
    # the tank's target physically unreachable (max inflow < new outflow), so
    # its own PI loop winds up to the 12 V ceiling and stays there. 11.0 V is
    # therefore above every healthy value yet below every leak value.
    EFFORT_SAT = 11.0

    flag1 = m1 >= EFFORT_SAT
    flag2 = m2 >= EFFORT_SAT

    # A leak is a plant fault: the loop is already saturated, so lowering the
    # setpoint cannot change the mass-balance-limited level, and if the target
    # ever became reachable the loop would desaturate and hide the fault. Keep
    # the nominal targets (within the allowed band) -> no restore gap.
    def clamp(sp):
        if sp < 0.05:
            return 0.05
        if sp > 0.48:
            return 0.48
        return sp

    sp1 = clamp(nominal_targets["tank1"])
    sp2 = clamp(nominal_targets["tank2"])

    labels = []
    if flag1:
        labels.append("tank1")
    if flag2:
        labels.append("tank2")
    if labels:
        diag = ("outlet-leak alarm on " + "/".join(labels) +
                " (own loop effort near pump saturation: tank1=%.2fV tank2=%.2fV)"
                % (m1, m2))
    else:
        diag = ("no leak: loops within healthy effort band "
                "(tank1=%.2fV tank2=%.2fV)" % (m1, m2))

    return {
        "diagnosis": diag,
        "adjusted_setpoints": {"tank1": sp1, "tank2": sp2},
        "anomaly_flags": {"tank1": flag1, "tank2": flag2},
    }
