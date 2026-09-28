# Reading List

Background reading for this project, organized by which part of the work each
piece speaks to. You've already read "Learning Beyond Gradients," which was
the main inspiration — everything below either sits in the same lineage
(LLM-guided program search) or explains a failure mode we actually hit while
building this (reward hacking/specification gaming), or is the literature
around the baseline we're ultimately comparing against (TD-MPC).

## LLM-guided program search — the core paradigm

This project's Layer 3 (an LLM proposing code, evaluated on a fixed battery,
kept only on improvement) is a small instance of a pattern these papers
established and scaled up.

**FunSearch** — Romera-Paredes, B. et al. "Mathematical discoveries from
program search with large language models." *Nature*, 2023.
https://www.nature.com/articles/s41586-023-06924-6
(blog: https://deepmind.google/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/)

The closest academic relative of `train_supervisor.py`'s loop: pair an LLM
with an automated evaluator in an evolutionary procedure — generate candidate
programs, score them, use the best to seed new candidates — applied to open
problems in combinatorics and bin-packing. Read this first: it's the cleanest
statement of "LLM as mutation operator over a program population, evaluator
as the only judge," which is exactly our `check_source` → `score_supervisor`
→ elitist-keep loop, minus the multi-tank control domain.

**AlphaEvolve** — Novikov, A. et al. "AlphaEvolve: A coding agent for
scientific and algorithmic discovery." arXiv:2506.13131, 2025.
https://arxiv.org/abs/2506.13131
(blog: https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/)

FunSearch scaled into a general-purpose evolutionary coding agent, notably
using a *cheaper/faster* model to maximize idea breadth and a *stronger*
model for depth on the same search — directly relevant to our own
flash-vs-v4-pro back-and-forth this project went through, and to the
(corrected) conclusion that search *infrastructure* — memory across trials,
generalization feedback — mattered more than raw model tier for us.

**Eureka** — Ma, Y.J. et al. "Eureka: Human-Level Reward Design via Coding
Large Language Models." ICLR 2024, arXiv:2310.12931.
https://arxiv.org/abs/2310.12931

An LLM writes *reward functions* (not policies) for RL tasks, evaluates them
by actually running RL with each candidate, and iterates using a "reward
reflection" step where it reads back numeric feedback from the last attempt.
That reflection step is essentially what our `relations_learned` /
context-report mechanism does — accumulating durable, reusable diagnostic
insight across trials instead of reasoning from scratch each time. Worth
reading specifically for how they structure that feedback loop.

## Reward hacking / specification gaming — why the anti-gaming guards exist

We independently rediscovered this failure mode this session (a candidate
"solving" the two-tank problem by flagging anomalies constantly, winning on
an *averaged* score while badly regressing a fault-free scenario) before
fixing it with per-scenario regression guards and asymmetric penalties. These
are the standard references for that failure class.

**Specification gaming: the flip side of AI ingenuity** — Krakovna, V. et al.
DeepMind blog + examples catalogue, 2020.
https://deepmind.google/blog/specification-gaming-the-flip-side-of-ai-ingenuity/

The canonical catalogue of "agent satisfies the literal objective, not the
intended one." The Coast Runners boat-racing example (an agent given reward
for hitting checkpoints learns to spin in circles hitting the same checkpoint
forever, forgoing the race entirely) is structurally identical to what we
found in the two-tank trainer, just in a game instead of a control loop.

**Concrete Problems in AI Safety** — Amodei, D., Olah, C., Steinhardt, J.,
Christiano, P., Schulman, J., Mané, D. arXiv:1606.06565, 2016.
https://arxiv.org/pdf/1606.06565

Older and more foundational: "avoiding reward hacking" as one of five
concrete, near-term AI safety problems, argued from first principles rather
than by example. Good for framing *why* this is a predictable, general
failure mode of any optimization process (LLM-guided search included) rather
than a one-off bug in our scoring function.

## The baseline we're ultimately compared against

**TD-MPC** — Hansen, N., Wang, X., Su, H. "Temporal Difference Learning for
Model Predictive Control." ICML 2022.
https://proceedings.mlr.press/v162/hansen22a/hansen22a.pdf

**TD-MPC2** — Hansen, N., Su, H., Wang, X. "TD-MPC2: Scalable, Robust World
Models for Continuous Control." ICLR 2024, arXiv:2310.16828.
https://arxiv.org/abs/2310.16828

Model-based RL that plans over short horizons in a learned latent world model
and bootstraps long-term value with TD learning. This is the black-box,
learned-controller side of the comparison this thesis sets up: interpretable,
security-checkable heuristic code (our approach) versus a high-performing but
opaque neural policy (TD-MPC/TD-MPC2). Read enough to be able to state
precisely what it can do that a hand-readable rule set can't (and vice
versa) — that contrast is the thesis's actual research question.

## Domain grounding: control in mineral processing

**A survey of grinding circuit control methods: from decentralized PID
controllers to multivariable predictive controllers** — Pomerleau, A.,
Hodouin, D., Desbiens, A., Gagnon, E. *Powder Technology*, vol. 108, 2000,
pp. 103–115. https://www.sciencedirect.com/science/article/abs/pii/S0032591099002077

Older but directly on-target: grinding circuits (the real mining unit
operation this toy leaky-tank/two-tank testbed is meant to eventually stand
in for) are multivariable, coupled, and disturbance-heavy in exactly the way
our two-tank cascade is a toy version of. Useful for grounding claims about
why PID-only control is insufficient in the real process, and what
"multivariable predictive control" was already doing before either MPC or
LLM-guided heuristics entered the picture.

## Benchmarks for the RL/TD-MPC comparison

Where to actually run a head-to-head once the toy testbeds are outgrown.
Both of these are runnable now (a MATLAB/Simulink license is available for
TEP).

**PC-Gym** — Bloor, M., Torraca, J., Sandoval, I.O., Ahmed, A., White, M.,
Mercangöz, M., Tsay, C., Del Rio Chanona, E.A., Mowbray, M. "PC-Gym:
Benchmark Environments For Process Control Problems." arXiv:2410.22093, 2024.
https://arxiv.org/abs/2410.22093
(code: https://github.com/MaximilianB2/pc-gym, PyPI: `pcgym`)

Best first stop: an open-source, pure-Python Gymnasium-style benchmark suite
built specifically for comparing RL controllers against Nonlinear MPC on
process-control problems (CSTRs, multistage extraction, crystallization
reactors), with nonlinear dynamics, disturbances, and constraints already
built in, and an NMPC oracle baseline included out of the box. No MATLAB
dependency, `pip install pcgym` and go. The most direct route to a real
RL-vs-(N)MPC-vs-our-supervisor comparison without building the harness
ourselves.

**Tennessee Eastman Process (TEP)** — original process: Downs, J.J., Vogel,
E.F. "A plant-wide industrial process control problem." *Computers &
Chemical Engineering*, vol. 17, 1993, pp. 245–255. Python interface: Reinartz,
C., Enevoldsen, T.T. "pyTEP: A Python package for interactive simulations of
the Tennessee Eastman process." *SoftwareX*, vol. 18, 2022, art. 101053.
https://www.sciencedirect.com/science/article/pii/S2352711022000449
(code: https://github.com/ccreinartz11/pytep — requires the MATLAB engine
for Python, i.e. a licensed MATLAB/Simulink install)

The historical gold-standard benchmark for fault detection/diagnosis and
plant-wide control in a large, coupled, multivariable chemical process (12
manipulated valves, 41 measurements, two simultaneous gas-liquid exothermic
reactions) — decades of published PID/MPC/RL/fault-detection results exist to
compare against. Thematically the closest match to what our supervisor is
actually doing (anomaly detection + multivariable setpoint coordination),
just at a much larger, industrially-realistic scale than the two-tank
cascade. `pyTEP` wraps the original Fortran/Simulink simulator so the
underlying process dynamics match the literature exactly, at the cost of
needing MATLAB/Simulink installed to run it.
