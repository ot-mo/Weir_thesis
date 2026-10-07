"""Sealed test battery for the pre-registered coordination protocol
(results/coordination/PROTOCOL.md).

It is never used by the trainer, the MPC tuning or the stress tests, and is
evaluated once, after the protocol runs, by evaluate_sealed_test.py, which logs
every access. The development, held-out and beyond batteries were looked at
after every redesign of the training loop and are validation sets now; this
battery is the clean test.

Parts (seed TEST_SEED, PER_CELL scenarios per cell, 183 scenarios):
- "dev": the development range with a new seed (6 nominal target changes and
  4 disturbance kinds x 3 patterns), for RQ1;
- "x1.25", "x1.5", "x2": the same kinds and patterns with amplitudes 1.25, 1.5
  and 2 times a draw from the development range, for the degradation curve of
  RQ2/C2 (pump-gain losses capped at 80 % and valve splits kept in
  [0.02, 0.98], so every scenario is physically valid);
- "unseen_period": sines at development amplitudes with periods outside the
  development range of 200-500 s (100-180 s and 550-800 s);
- "unseen_combination": feed, pump and split disturbances together (the
  development battery combines two kinds), each at 0.6 times a development
  amplitude.

The battery is defined by its seed and this code. EXPECTED_FINGERPRINT is the
SHA-256 of every scenario's parameters; make_test_battery() refuses to return a
battery that does not match it, so a change to this file or to the
disturbance definitions in four_tank_coordination.py cannot alter the test set
silently.
"""

import dataclasses
import hashlib
import json

import numpy as np

import four_tank_coordination as C

TEST_SEED = 7351          # not used by any other battery
PER_CELL = 3
BEYOND_LEVELS = (1.25, 1.5, 2.0)
UNSEEN_PERIODS = {"short": (100.0, 180.0), "long": (550.0, 800.0)}
KINDS = ("feed", "pump", "split")
EXPECTED_FINGERPRINT = "867c37cfc2af1bbc4b64f59c6af949d9eb354bcaa02c1ea52f95a34cbd9747e0"


def _physical(dist):
    """Cap a disturbance so the plant stays physically valid (nominal gamma 0.2)."""
    p = C.plant_params()
    a = dist.amplitude
    if dist.kind.startswith("pump"):
        a = max(a, -0.8)
    elif dist.kind.startswith("split"):
        g = p["gamma_1"] if dist.kind == "split1" else p["gamma_2"]
        a = min(max(a, 0.02 - g), 0.98 - g)
    return dataclasses.replace(dist, amplitude=float(a))


def _disturbance(rng, kind_label, pattern, scale=1.0, period=(200.0, 500.0)):
    kind, sign, dev, _ = C.DISTURBANCE_CHANNELS[kind_label][rng.integers(len(C.DISTURBANCE_CHANNELS[kind_label]))]
    d = C.Disturbance(kind=kind, pattern=pattern, amplitude=float(sign * rng.uniform(*dev) * scale),
                      onset_s=float(rng.uniform(150, 300)), ramp_s=float(rng.uniform(200, 400)),
                      period_s=float(rng.uniform(*period)))
    return _physical(d)


def _scenario(name, dists, range_label, kind_label, pattern_label, seed):
    return C.CoordinationScenario(name=name, disturbances=tuple(dists), range_label=range_label,
                                  kind_label=kind_label, pattern_label=pattern_label,
                                  events=tuple(sorted(d.onset_s for d in dists)), seed=seed)


def _build():
    rng = np.random.default_rng(TEST_SEED + 1)
    battery = [dataclasses.replace(s, name=f"test_{s.name}") for s in C.make_battery("dev", PER_CELL, TEST_SEED)]
    seed = TEST_SEED * 10
    for level in BEYOND_LEVELS:
        for i in range(PER_CELL):
            for kind_label in KINDS + ("combined",):
                for pattern in C.PATTERNS:
                    if kind_label == "combined":
                        first, second = rng.choice(list(KINDS), size=2, replace=False)
                        dists = [_disturbance(rng, first, pattern, 0.75 * level),
                                 _disturbance(rng, second, pattern, 0.75 * level)]
                    else:
                        dists = [_disturbance(rng, kind_label, pattern, level)]
                    seed += 1
                    battery.append(_scenario(f"test_x{level:g}_{kind_label}_{pattern}_{i}", dists, f"x{level:g}",
                                             kind_label, pattern, seed))
    for band, period in UNSEEN_PERIODS.items():
        for i in range(PER_CELL):
            for kind_label in KINDS + ("combined",):
                if kind_label == "combined":
                    first, second = rng.choice(list(KINDS), size=2, replace=False)
                    dists = [_disturbance(rng, first, "sine", 0.75, period), _disturbance(rng, second, "sine", 0.75, period)]
                else:
                    dists = [_disturbance(rng, kind_label, "sine", 1.0, period)]
                seed += 1
                battery.append(_scenario(f"test_period_{band}_{kind_label}_{i}", dists, "unseen_period",
                                         kind_label, f"sine_{band}", seed))
    for i in range(PER_CELL):
        for pattern in C.PATTERNS:
            dists = [_disturbance(rng, k, pattern, 0.6) for k in KINDS]
            seed += 1
            battery.append(_scenario(f"test_triple_{pattern}_{i}", dists, "unseen_combination", "triple", pattern, seed))
    return battery


def fingerprint(battery=None):
    battery = _build() if battery is None else battery
    rows = [{"name": s.name, "range": s.range_label, "kind": s.kind_label, "pattern": s.pattern_label, "seed": s.seed,
             "events": [round(e, 9) for e in s.events],
             "targets": [[round(t, 9), round(q, 9)] for t, q in s.target_changes],
             "disturbances": [[d.kind, d.pattern, round(d.amplitude, 9), round(d.onset_s, 9), round(d.ramp_s, 9),
                               round(d.period_s, 9)] for d in s.disturbances],
             "sim": [s.sim_time, s.dt, s.window_steps, s.decision_interval_steps]} for s in battery]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()


def make_test_battery(unseal=False):
    """The sealed battery. Only evaluate_sealed_test.py should pass unseal=True,
    after logging the access."""
    if not unseal:
        raise PermissionError("the test battery is sealed; evaluate it with evaluate_sealed_test.py --unseal REASON")
    battery = _build()
    found = fingerprint(battery)
    if EXPECTED_FINGERPRINT is not None and found != EXPECTED_FINGERPRINT:
        raise RuntimeError(f"test battery changed: fingerprint {found[:16]} != frozen {EXPECTED_FINGERPRINT[:16]}")
    return battery


def summary():
    """Composition only (names, ranges, counts) - no evaluation."""
    battery = _build()
    counts = {}
    for s in battery:
        counts[s.range_label] = counts.get(s.range_label, 0) + 1
    return len(battery), counts, fingerprint(battery)


if __name__ == "__main__":
    n, counts, fp = summary()
    print(f"{n} scenarios: {counts}\nfingerprint {fp}")
