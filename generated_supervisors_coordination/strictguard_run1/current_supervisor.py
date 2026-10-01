def supervise(telemetry_window, active_setpoints, objectives):
    # Fixed operating recipe (the PID-only baseline as code): the nominal
    # setpoints scaled to the production target with Q ~ sqrt(h). Disturbances
    # are not handled.
    NOMINAL_H1 = 0.30
    NOMINAL_H2 = 0.35
    NOMINAL_PRODUCTION = 16.35286638873749  # L/s at the nominal setpoints
    scale = (objectives["production_target"] / NOMINAL_PRODUCTION) ** 2
    lo, hi = objectives["setpoint_limits"]
    h1 = min(hi, max(lo, NOMINAL_H1 * scale))
    h2 = min(hi, max(lo, NOMINAL_H2 * scale))
    return {
        "diagnosis": "fixed recipe: setpoints scaled to the production target",
        "adjusted_setpoints": {"h1": h1, "h2": h2},
    }
