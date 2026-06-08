<!--
Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
SPDX-License-Identifier: Apache-2.0
-->

# Corexiom v2 — Core Design

A redesign of the reasoning core based on two principles: **hybridize** (the
neural side populates, the symbolic side verifies) and **ground** (replace
heuristics with a defined semantics and explicit guarantees).

This document scrupulously distinguishes what is **proven by construction**,
what is **guaranteed**, and what is only **empirically validated**. This is
the heart of the project's honesty: we do not claim a soundness we have not
demonstrated.

---

## 1. Model

The world is a set of atomic **assertions**, each carrying a *degree of belief*
`bel ∈ [0, 1]`. Two statuses are distinguished:

- **Axiom** (`Status.AXIOM`): belief locked at `1.0`, **inviolable**.
  A hard constraint. Violating it = hard incoherence (provable).
- **Belief** (`Status.BELIEF`): revisable degree in `[0, 1]`, starting from a
  *prior* `prior`.

Assertions are connected by typed **links** (`Relation`):

| Relation | Semantics | Effect on propagation |
|---|---|---|
| `IMPLIES(a→b, w)` | if `a` then `b` | raises the target of `b` |
| `SUPPORTS(a→b, w)` | `a` is evidence for `b` | raises the target of `b` (more weakly) |
| `CONTRADICTS(a,b,w)` | `a` and `b` cannot both be true | lowers the target of each; conflict |

`CONTRADICTS` is symmetric (registered in both directions).

Every conclusion produced by the engine carries a **justification**
(`Justification`) listing the assertions and links that ground it: this is
native explainability.

---

## 2. Propagation semantics

Let `bel_k` be the state (belief vector) at iteration `k`. For each non-axiom
assertion `a` with prior `p_a`:
support(a)  = Σ  bel_k[s] · w      over links (s → a) of type IMPLIES or SUPPORTS
conflict(a) = Σ  bel_k[c] · w      over links (c — a) of type CONTRADICTS
target(a)   = clamp( p_a + G⁺·support(a) − G⁻·conflict(a) , 0, 1 )
bel_{k+1}[a] = (1 − λ)·bel_k[a] + λ·target(a)          with λ ∈ (0, 1]

For axioms: `bel_{k+1} = bel_k = 1.0`.

**Dynamics parameters** (set in the `ReasoningEngine` constructor, all
configurable, with safe and damped defaults):

| Parameter | Symbol | Default | Role |
|---|---|---|---|
| `gain_support`  | G⁺ | `0.6`   | weight of evidence (`IMPLIES`/`SUPPORTS`) on the target |
| `gain_conflict` | G⁻ | `0.8`   | weight of contradictions (`CONTRADICTS`) on the target |
| `relax`         | λ  | `0.5`   | damping of the update, in `(0, 1]` |
| `epsilon`       | ε  | `1e-9`  | fixed-point detection threshold |
| `max_iters`     | —  | `1000`  | iteration cap (termination) |

Choosing `G⁻ > G⁺` (0.8 > 0.6) is **deliberate**: the engine weights conflict
more heavily than support. This is **prudence by design** — when in doubt,
it downgrades a belief rather than inflating it. This is the numerical
translation of the principle *"suspend rather than hallucinate"*. The G⁻/G⁺
ratio tunes the engine's temperament (more cautious as it grows).

**Synchronous update (Jacobi)**: all targets are computed from the *same*
snapshot `bel_k`. This is what yields order independence.

We iterate until `max_k |bel_{k+1} − bel_k| < ε` (fixed point reached) or
until `max_iters` (guaranteed termination).

### Guarantees

| Property | Status | Justification |
|---|---|---|
| **Bounds** `bel ∈ [0,1]` | ✅ proven | `clamp` at every step; initialisation in `[0,1]` |
| **Axiom preservation** | ✅ proven | axioms are never updated |
| **Determinism** | ✅ proven | no source of randomness |
| **Order independence** | ✅ proven | synchronous update from `bel_k` |
| **Termination** | ✅ guaranteed | `max_iters` cap |
| **Convergence to a fixed point** | 🔬 validated | relaxation `λ<1` (damping); verified on thousands of randomly generated graphs (property-based tests) |

> Honest disclaimer: we do **not** claim an analytical proof of universal
> convergence for every graph. We guarantee *termination* and demonstrate
> *empirically* (property-based testing) that at halt, the state is a
> quasi-fixed point (reapplying the operator moves it by less than `ε`).

> **Convergence regime (measured).** Convergence is observed reliably only
> in the **damped regime** (λ ≲ 0.5, the default). At λ ≥ 0.8, on graphs
> with strong contradictions, the operator may **oscillate** and reach the
> `max_iters` cap without a fixed point — **without ever violating termination
> or the `[0, 1]` bounds**. In other words: damping is what *buys* convergence.
> The upper bound `λ = 1` is still permitted but discouraged for this reason.

---

## 3. Coherence

- **Hard coherence** (`bool`) — exactly decidable. `False` if there exists a
  `CONTRADICTS` link between **two axioms**: two inviolable, mutually exclusive
  propositions cannot coexist. The proof is the pair of axioms and the link.
- **Soft coherence score** ∈ `[0,1]`:
conflict_mass = Σ  bel[a]·bel[b]·w   over CONTRADICTS links (counted once)
coherence     = 1 − clamp( conflict_mass / Σw , 0, 1 )

Bounded by construction: `0 ≤ coherence ≤ 1` (proven).

---

## 4. Decision and suspension (grounded)

`decide(threshold θ, margin δ)` selects the **actionable** assertion with the
highest belief `≥ θ`, unless suspended. Suspension rules, in order, each
returning a justification:

- **S1 — `AXIOM_CONFLICT`**: hard incoherence detected. We do not decide on
  a contradictory foundation.
- **S2 — `VIOLATES_AXIOM`**: an action in direct `CONTRADICTS` with an axiom
  is **structurally excluded** from the candidates (keeping it would violate
  an inviolable constraint). This verdict is only returned if **no permitted
  action remains viable** *and* a serious action (prior `≥ θ`) was excluded
  this way: if a permitted option exists above the threshold, the engine
  prefers it (cf. `test_allowed_preferred_over_forbidden`).
- **S3 — `AMBIGUOUS`**: `bel(top₁) − bel(top₂) < δ`. The system does not
  break a near-tie: it suspends rather than fabricating a preference.
- Otherwise **`DECIDED`**: `top₁`, with its justification (support chain).
- No candidate `≥ θ` → **`INSUFFICIENT_BELIEF`** (no forced decision).

> **Actual precedence.** Excluding a forbidden action is a *structural fact*,
> applied **before** choosing among candidates: an action contradicting an
> axiom is never selected, regardless of its belief. The effective hierarchy
> is therefore: `AXIOM_CONFLICT` (foundation) → exclusion of forbidden
> actions → `AMBIGUOUS`/`DECIDED` among permitted ones → `VIOLATES_AXIOM`
> (if a serious action was excluded and nothing permitted remains) →
> `INSUFFICIENT_BELIEF`.

> **Weight independence.** The prohibition depends on the *existence* of a
> `CONTRADICTS` link to an axiom, **not on its weight**: even a minimal
> weight forbids the action. The weight of a `CONTRADICTS` link only acts on
> propagation (§2) and the soft coherence score (§3); against an axiom, the
> constraint is *hard*, hence binary.

This is the embodiment of the founding principle: *suspend rather than
hallucinate*, but on explicit and traceable criteria.

---

## 5. Hybridization: pluggable perception
Perceiver (protocol)
├─ RuleBasedPerceiver   — pattern-based extraction (default, no dependencies)
└─ LLMPerceiver         — interface for a neural model (populates the graph)

The engine does **not** depend on how assertions are produced. An LLM can
turn natural language into structured assertions (the neural side *proposes*);
the engine *verifies* them, detects contradictions, and suspends if needed
(the symbolic side *constrains*). The neural component never has the final
say on coherence.

---

## 6. What this core is not (honest disclaimer)

- This is **not** a general-purpose AI nor a substitute for language models.
  The `RuleBasedPerceiver` remains a simple parser; serious grounding goes
  through an `LLMPerceiver`. The core is a **reasoning and safeguard layer**.
- The propagation semantics is grounded and stable, but it is not a complete
  logical prover (SAT/SMT) nor exact Bayesian inference. This is a deliberate
  choice: a simple, predictable, verifiable operator on top of which more
  formal layers can be grafted.
- "Sound" here means: properties proven where they can be, aggressively
  validated elsewhere (property-based + adversarial tests), no hidden state,
  fully traceable. Not "unbreakable" — such a notion does not exist.