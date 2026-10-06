# Reading List

Sources for the thesis, grouped by topic.

## Starting point

**Learning Beyond Gradients**: Weng, J. Blog post, 2026.
https://trinkle23897.github.io/learning-beyond-gradients/
Describes improving a policy with a coding agent that inspects execution traces, replays and
failure modes and rewrites code, instead of through gradient updates. Recommends simplifying the
code after every new best score and checking that the score does not regress.

**PromptPO**: Hatgis-Kessell, S., Brunskill, E. "When are LLMs sufficient policy optimizers for
sequential RL tasks?" arXiv:2605.30719, 2026. https://arxiv.org/abs/2605.30719
Prompts an LLM with Python descriptions of the state space, action space and reward function and
refines executable policies from rollout feedback. The resulting policies range from tuned
proportional controllers to rule-based plans.

## LLM-guided program search and evolution

**FunSearch**: Romera-Paredes, B. et al. "Mathematical discoveries from program search with large
language models." *Nature* 625, 468–475, 2024. https://www.nature.com/articles/s41586-023-06924-6
Pairs an LLM with an automated evaluator in an evolutionary loop over programs, with the
evaluator as the only judge. Found new cap set constructions and better online bin-packing
heuristics.

**AlphaEvolve**: Novikov, A. et al. "AlphaEvolve: A coding agent for scientific and algorithmic
discovery." arXiv:2506.13131, 2025. https://arxiv.org/abs/2506.13131
Evolutionary coding agent that combines a fast model for breadth with a stronger model for depth,
and proposes changes as diffs against a parent program rather than whole new programs.

**Evolution through Large Models (ELM)**: Lehman, J., Gordon, J., Jain, S., Ndousse,
K., Yeh, C., Stanley, K.O. arXiv:2206.08896, 2022. https://arxiv.org/abs/2206.08896
An early statement of the LLM as a mutation operator in genetic programming. A code model
mutates programs inside MAP-Elites to generate walking robots in the Sodarace domain.

**OPRO**: Yang, C. et al. "Large Language Models as Optimizers." ICLR 2024, arXiv:2309.03409.
https://arxiv.org/abs/2309.03409
The LLM is shown earlier solutions with their scores in a meta-prompt and asked for a better one.
Applied to linear regression, the travelling salesman problem and prompt optimization.

**Evolution of Heuristics (EoH)**: Liu, F. et al. "Evolution of Heuristics: Towards Efficient
Automatic Algorithm Design Using Large Language Model." ICML 2024, arXiv:2401.02051.
https://arxiv.org/abs/2401.02051
Evolves a natural-language description of each heuristic together with its code, on online bin
packing, travelling salesman and flow-shop scheduling.

**ReEvo**: Ye, H. et al. "ReEvo: Large Language Models as Hyper-Heuristics with Reflective
Evolution." NeurIPS 2024, arXiv:2402.01145. https://arxiv.org/abs/2402.01145
Combines evolutionary search over heuristics with LLM-written reflections that act as "verbal
gradients", across several combinatorial optimization problems.

**ShinkaEvolve**: Lange, R.T., Imajuku, Y., Cetin, E. "ShinkaEvolve: Towards
Open-Ended and Sample-Efficient Program Evolution." arXiv:2509.19349, 2025.
https://arxiv.org/abs/2509.19349 (code: https://github.com/SakanaAI/ShinkaEvolve)
An open-source framework aimed at sample efficiency. It uses adaptive parent sampling, rejects
code proposals that are too similar to earlier ones, and chooses between several LLMs with a
bandit. Reports a new circle-packing solution from about 150 samples.

**Darwin Gödel Machine**: Zhang, J., Hu, S., Lu, C., Lange, R., Clune, J. "Darwin
Gödel Machine: Open-Ended Evolution of Self-Improving Agents." arXiv:2505.22954, 2025.
https://arxiv.org/abs/2505.22954
A coding agent that edits its own code and keeps an archive of all variants instead of a single
champion. This is the open-ended alternative to an elitist hill-climb.

**Simple Baselines are Competitive with Code Evolution**: Gideoni, Y., Risi, S.,
Gal, Y. ICLR 2026, arXiv:2602.16805. https://arxiv.org/abs/2602.16805
Finds that simple baselines match or beat sophisticated code-evolution pipelines on mathematical
bounds, agent scaffolds and ML competitions. The search space and the domain knowledge in the
prompt set the performance ceiling more than the evolution machinery does.

**What Do Evolutionary Coding Agents Evolve?**: Pelleriti, N., Nelaturu, S.H., Zhou,
Z., Li, Z., Zimmer, M., Han, B., Pokutta, S. arXiv:2605.20086, 2026.
https://arxiv.org/abs/2605.20086
Replays evolutionary coding traces from four frameworks and classifies the edits behind score
gains: bug fixes, re-tuned constants, recombination, re-introduced code and new structure. Only
some benchmark gains correspond to new algorithmic structure.

## LLMs writing rewards, policies and controller code

**Eureka**: Ma, Y.J. et al. "Eureka: Human-Level Reward Design via Coding Large Language Models."
ICLR 2024, arXiv:2310.12931. https://arxiv.org/abs/2310.12931
An LLM writes reward functions for reinforcement learning, each evaluated by training a policy
with it. Numeric training statistics are fed back in a "reward reflection" step.

**Code as Policies**: Liang, J. et al. "Code as Policies: Language Model Programs for Embodied
Control." ICRA 2023, arXiv:2209.07753. https://arxiv.org/abs/2209.07753
An LLM writes robot policy code that calls perception and control APIs, including feedback
loops; the generated program is itself the policy.

**LLM4PLC**: Fakih, M., Dharmaji, R., Moghaddas, Y., Quiros, G., Ogundare, O., Al
Faruque, M.A. "LLM4PLC: Harnessing Large Language Models for Verifiable Programming of PLCs in
Industrial Control Systems." ICSE-SEIP 2024, arXiv:2401.05443. https://arxiv.org/abs/2401.05443
A pipeline that passes LLM-generated PLC programs through grammar checkers, compilers and an SMV
model checker, with feedback, before use. An industrial counterpart to gating generated code with
security checks.

## Feedback, memory and self-correction

**Reflexion**: Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K., Yao, S. "Reflexion: Language
Agents with Verbal Reinforcement Learning." NeurIPS 2023, arXiv:2303.11366.
https://arxiv.org/abs/2303.11366
Agents write verbal reflections on failed attempts into a memory that conditions later attempts.

**Trace**: Cheng, C.-A., Nie, A., Swaminathan, A. "Trace is the Next AutoDiff:
Generative Optimization with Rich Feedback, Execution Traces, and LLMs." NeurIPS 2024,
arXiv:2406.16218. https://arxiv.org/abs/2406.16218
Treats a workflow's execution trace as the analogue of a back-propagated gradient. An LLM
optimizer updates code and prompts from the trace plus feedback.

**Large Language Models Cannot Self-Correct Reasoning Yet**: Huang, J. et al. ICLR
2024, arXiv:2310.01798. https://arxiv.org/abs/2310.01798
Without external feedback, LLMs do not reliably correct their own reasoning and sometimes get
worse. Earlier reported gains depended on oracle labels. Relevant to keeping only measured
results, not the model's own unverified lessons.

## Interpretable and programmatic policies

**Programmatically Interpretable Reinforcement Learning (PIRL)**: Verma, A., Murali,
V., Singh, R., Kohli, P., Chaudhuri, S. ICML 2018, arXiv:1804.02477.
https://arxiv.org/abs/1804.02477
Searches for policies as programs in a small domain-specific language, guided by a neural
policy, on the TORCS racing simulator. The resulting programs are readable controllers that can
be inspected and verified.

**VIPER**: Bastani, O., Pu, Y., Solar-Lezama, A. "Verifiable Reinforcement Learning
via Policy Extraction." NeurIPS 2018, arXiv:1805.08328. https://arxiv.org/abs/1805.08328
Extracts decision-tree policies from neural policies so that properties such as correctness,
robustness and stability can be verified.

**Stop explaining black box models**: Rudin, C. "Stop explaining black box machine learning
models for high stakes decisions and use interpretable models instead." *Nature Machine
Intelligence* 1, 206–215, 2019. https://www.nature.com/articles/s42256-019-0048-x
Argues that in high-stakes settings, interpretable models should be preferred to post-hoc
explanations of black boxes. Frames the readable-code-versus-neural-policy contrast.

## Specification gaming and overfitting to the evaluator

**Specification gaming: the flip side of AI ingenuity**: Krakovna, V. et al. DeepMind blog and
example catalogue, 2020.
https://deepmind.google/blog/specification-gaming-the-flip-side-of-ai-ingenuity/
A catalogue of agents that satisfy the literal objective rather than the intended one, such as
the CoastRunners boat circling to collect the same reward targets instead of finishing the race.

**Concrete Problems in AI Safety**: Amodei, D., Olah, C., Steinhardt, J., Christiano, P.,
Schulman, J., Mané, D. arXiv:1606.06565, 2016. https://arxiv.org/abs/1606.06565
Presents reward hacking as one of five concrete AI-safety problems, a predictable property of any
optimization against a proxy objective.

**The Surprising Creativity of Digital Evolution**: Lehman, J. et al. *Artificial
Life* 26(2), 2020, arXiv:1803.03453. https://arxiv.org/abs/1803.03453
First-hand anecdotes of evolutionary algorithms exploiting simulator bugs and badly specified
fitness functions. The same failure class, in evolutionary search specifically.

**The reusable holdout**: Dwork, C., Feldman, V., Hardt, M., Pitassi, T., Reingold,
O., Roth, A. "The reusable holdout: Preserving validity in adaptive data analysis." *Science*
349(6248), 636–638, 2015. https://www.science.org/doi/10.1126/science.aaa9375
Shows that repeatedly consulting a holdout set while making choices leaks information and
invalidates it as an unbiased test. Relevant to showing an optimizer the dev-vs-held-out gap.

**Do ImageNet Classifiers Generalize to ImageNet?**: Recht, B., Roelofs, R.,
Schmidt, L., Shankar, V. ICML 2019, arXiv:1902.10811. https://arxiv.org/abs/1902.10811
Builds new test sets with the original collection protocol. Accuracy drops noticeably, while
model rankings are largely preserved. An empirical look at the gap between the benchmark used
for selection and fresh samples from the same distribution.

## Supervisory control, setpoint optimization and MPC practice

**Self-optimizing control**: Skogestad, S. "Plantwide control: the search for the
self-optimizing control structure." *Journal of Process Control* 10, 487–507, 2000.
https://skoge.folk.ntnu.no/publications/2000/self1/self1.pdf
How to choose the controlled variables whose constant setpoints keep operation near-optimal under
disturbances. The classical theory of what a supervisory layer above regulatory loops should
hold constant.

**Real-time optimization (RTO)**: Darby, M.L., Nikolaou, M., Jones, J., Nicholson, D. "RTO: An
overview and assessment of current practice." *Journal of Process Control* 21(6), 874–884, 2011.
Industrial practice of model-based setpoint optimization above the control layer: steady-state
detection, data reconciliation, model updating and optimization. The classical counterpart of a
setpoint-only supervisor.

**Industrial MPC survey**: Qin, S.J., Badgwell, T.A. "A survey of industrial model predictive
control technology." *Control Engineering Practice* 11(7), 733–764, 2003.
The standard overview of how MPC is configured and used in industry.

**Offset-free MPC**: Muske, K.R., Badgwell, T.A. "Disturbance modeling for
offset-free linear model predictive control." *Journal of Process Control* 12, 617–632, 2002.
Augments the plant model with disturbance states estimated by an observer, so that MPC removes
steady-state offset. The theory behind the bias-update disturbance estimate in the MPC baseline.

## Oscillation detection and loop monitoring

**A control-loop performance monitor**: Hägglund, T. *Control Engineering Practice*
3(11), 1543–1551, 1995. https://doi.org/10.1016/0967-0661(95)00164-P
Detects oscillating loops automatically by integrating the absolute control error between zero
crossings and counting large excursions, using only the normal controller parameters. A
reference point for supervisors that must tell sustained oscillations from steps.

**Detection and diagnosis of oscillation in control loops**: Thornhill, N.F.,
Hägglund, T. *Control Engineering Practice* 5(10), 1343–1354, 1997.
Operational signatures that indicate the cause of a loop oscillation and which test to run to
confirm it.

## Model-based reinforcement learning baseline

**TD-MPC**: Hansen, N., Wang, X., Su, H. "Temporal Difference Learning for Model Predictive
Control." ICML 2022. https://proceedings.mlr.press/v162/hansen22a/hansen22a.pdf

**TD-MPC2**: Hansen, N., Su, H., Wang, X. "TD-MPC2: Scalable, Robust World Models for Continuous
Control." ICLR 2024, arXiv:2310.16828. https://arxiv.org/abs/2310.16828

Model-based RL that plans over a short horizon in a learned latent world model and bootstraps
long-term value with temporal-difference learning. The learned, opaque side of the comparison
with readable, security-checked supervisory code.

## Process control and mineral processing

**Grinding circuit control survey**: Pomerleau, A., Hodouin, D., Desbiens, A., Gagnon, É. "A survey
of grinding circuit control methods: from decentralized PID controllers to multivariable
predictive controllers." *Powder Technology* 108, 103–115, 2000.
Grinding circuits are multivariable, coupled and disturbance-heavy. The survey covers control
from decentralized PID to multivariable predictive control.

**Grinding mill circuits: control and economics**: Wei, D., Craig, I.K. "Grinding mill circuits –
A survey of control and economic concerns." *International Journal of Mineral Processing* 90,
56–66, 2009.
An industry survey of how milling circuits are controlled and how key process variables link to
economic benefit.

**Control, observation and optimization in mineral processing**: Hodouin, D. "Methods for
automatic control, observation, and optimization in mineral processing plants." *Journal of
Process Control* 21(2), 211–225, 2011.
A review noting that PID still dominates mineral processing despite decades of advanced-control
research. Calls for a hierarchical view that integrates sensors, observers, controllers and
optimizers.

**Run-of-mine grinding circuit model**: le Roux, J.D., Craig, I.K., Hulbert, D.G.,
Hinde, A.L. "Analysis and validation of a run-of-mine ore grinding mill circuit model for process
control." *Minerals Engineering* 43–44, 121–134, 2013.
https://doi.org/10.1016/j.mineng.2012.10.009
A compact nonlinear model with feeder, mill, sump and hydrocyclone modules, built for control
studies. A candidate next test bed between the four-tank process and a full plant simulator.

**Quadruple-tank process**: Johansson, K.H. "The quadruple-tank process: A multivariable
laboratory process with an adjustable zero." *IEEE Transactions on Control Systems Technology*
8(3), 456–465, 2000.
The laboratory process behind the four-tank test bed, with interacting loops and a zero whose
location depends on the valve split.

**Relative gain array**: Bristol, E.H. "On a new measure of interaction for multivariable process
control." *IEEE Transactions on Automatic Control* 11(1), 133–134, 1966.
The interaction measure used to choose input-output pairings for decentralized loops.

## Benchmarks

**PC-Gym**: Bloor, M. et al. "PC-Gym: Benchmark Environments For Process Control Problems."
arXiv:2410.22093, 2024. https://arxiv.org/abs/2410.22093 (code:
https://github.com/MaximilianB2/pc-gym)
An open-source Python suite of process-control environments with disturbances, constraints and a
nonlinear-MPC oracle, built for comparing RL controllers with NMPC. The source of the four-tank
model.

**Tennessee Eastman Process**: Downs, J.J., Vogel, E.F. "A plant-wide industrial process control
problem." *Computers & Chemical Engineering* 17, 245–255, 1993. Python interface: Reinartz, C.,
Enevoldsen, T.T. "pyTEP: A Python package for interactive simulations of the Tennessee Eastman
process." *SoftwareX* 18, 101053, 2022. https://github.com/ccreinartz11/pytep
The standard plant-wide benchmark for fault detection and multivariable control, with decades of
published results. pyTEP requires a MATLAB/Simulink installation.

## Sandboxing generated code

**Eval really is dangerous**: Batchelder, N. Blog post, 2012.
https://nedbatchelder.com/blog/201206/eval_really_is_dangerous
Shows how Python code run with an emptied namespace can still reach `__import__` and other
internals through object attributes. The reason a restricted `exec` needs AST checks on dunder
access, not just removed builtins.
