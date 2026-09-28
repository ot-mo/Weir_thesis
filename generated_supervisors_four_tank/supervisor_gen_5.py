def supervise(telemetry_window, active_setpoints, nominal_targets):
    """Supervisor for the quadruple-tank (Johansson) benchmark.

    Detection uses the cross-branch specific-effort ratio
        r = (v1 / sqrt(h1)) / (v2 / sqrt(h2))
    compared against the plant-geometry reference that holds at ANY steady
    operating point of this symmetric, cross-dominant (gamma = 0.2) plant:

        r_ref = (b*u2/u1 - a) / (b*u1/u2 - a),   a = gamma, b = 1 - gamma

    A tank-1 leak makes pump 1 back off and pump 2 take over, so r falls;
    a tank-2 leak does the mirror image and r rises.  The statistic needs no
    fault-free interval inside the window, so it also fires on faults that
    are already active in the very first sample of the window.
    """

    def _num(container, key, default):
        try:
            return float(container[key])
        except Exception:
            return float(default)

    def _median(values):
        ordered = sorted(values)
        count = len(ordered)
        if count == 0:
            return 0.0
        middle = count // 2
        if count % 2 == 1:
            return ordered[middle]
        return 0.5 * (ordered[middle - 1] + ordered[middle])

    setpoint1 = _num(active_setpoints, "tank1", 0.30)
    setpoint2 = _num(active_setpoints, "tank2", 0.30)
    nominal1 = _num(nominal_targets, "tank1", setpoint1)
    nominal2 = _num(nominal_targets, "tank2", setpoint2)

    unchanged = {
        "diagnosis": "insufficient telemetry, no anomaly assumed",
        "adjusted_setpoints": {"tank1": setpoint1, "tank2": setpoint2},
        "anomaly_flags": {"tank1": False, "tank2": False},
    }

    try:
        rows = []
        if isinstance(telemetry_window, (list, tuple)):
            for sample in telemetry_window:
                if not isinstance(sample, dict):
                    continue
                branch1 = sample.get("tank1")
                branch2 = sample.get("tank2")
                if not isinstance(branch1, dict) or not isinstance(branch2, dict):
                    continue
                try:
                    effort1 = float(branch1["pump_effort"])
                    level1 = float(branch1["level"])
                    error1 = abs(float(branch1["error"]))
                    effort2 = float(branch2["pump_effort"])
                    level2 = float(branch2["level"])
                    error2 = abs(float(branch2["error"]))
                except Exception:
                    continue
                if level1 > 1e-9 and level2 > 1e-9 and effort1 > 0.0 and effort2 > 0.0:
                    rows.append((effort1, level1, error1, effort2, level2, error2))

        if len(rows) < 5:
            return unchanged

        GAMMA = 0.2
        A = GAMMA
        B = 1.0 - GAMMA

        deviations = []
        for (effort1, level1, error1, effort2, level2, error2) in rows:
            u1 = math.sqrt(level1)
            u2 = math.sqrt(level2)
            numerator = B * (u2 / u1) - A
            denominator = B * (u1 / u2) - A
            if numerator <= 1e-6 or denominator <= 1e-6:
                continue
            reference = numerator / denominator
            if reference <= 1e-6:
                continue
            measured = (effort1 / u1) / (effort2 / u2)
            deviations.append(measured / reference)

        if len(deviations) < 5:
            return unchanged

        m = len(deviations)
        quarter = max(3, m // 4)
        half = max(4, m // 2)
        recent_ratio = _median(deviations[-quarter:])
        mid_ratio = _median(deviations[-half:])
        recent_rows = rows[-quarter:]
        recent_error1 = _median([row[2] for row in recent_rows])
        recent_error2 = _median([row[5] for row in recent_rows])

        # Fixed RELATIVE band around the model-implied healthy value 1.0:
        # the healthy limit cycle stays inside it, a single-branch leak
        # (~20-35% ratio shift) crosses it.
        LOW_STRICT = 0.86
        LOW_LOOSE = 0.93
        HIGH_STRICT = 1.16
        HIGH_LOOSE = 1.07
        ERROR_GATE = 0.10

        tank1_anomaly = (recent_ratio < LOW_STRICT
                         and mid_ratio < LOW_LOOSE
                         and recent_error1 < ERROR_GATE)
        tank2_anomaly = (recent_ratio > HIGH_STRICT
                         and mid_ratio > HIGH_LOOSE
                         and recent_error2 < ERROR_GATE)

        LOWER_STEP = 0.010
        RESTORE_STEP = 0.005
        MAX_DROP = 0.02
        MIN_SETPOINT = 0.05

        def next_setpoint(setpoint, nominal, anomalous):
            if anomalous:
                floor = nominal - MAX_DROP
                if floor < MIN_SETPOINT:
                    floor = MIN_SETPOINT
                if setpoint > floor:
                    return max(floor, setpoint - LOWER_STEP)
                return setpoint
            if setpoint < nominal:
                return min(nominal, setpoint + RESTORE_STEP)
            return setpoint

        new_setpoint1 = next_setpoint(setpoint1, nominal1, tank1_anomaly)
        new_setpoint2 = next_setpoint(setpoint2, nominal2, tank2_anomaly)

        diagnosis = (
            "twinned specific-effort ratio recent=%.3f mid=%.3f (healthy 1.0); "
            "tank1 anomaly=%s, tank2 anomaly=%s"
            % (recent_ratio, mid_ratio, tank1_anomaly, tank2_anomaly)
        )

        return {
            "diagnosis": diagnosis,
            "adjusted_setpoints": {"tank1": new_setpoint1, "tank2": new_setpoint2},
            "anomaly_flags": {"tank1": tank1_anomaly, "tank2": tank2_anomaly},
        }
    except Exception:
        return unchanged
