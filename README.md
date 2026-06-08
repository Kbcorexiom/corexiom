<!--
Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
SPDX-License-Identifier: Apache-2.0
-->

<!--
Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
SPDX-License-Identifier: Apache-2.0
-->

# Corexiom v2 — Reasoning Core

A redesign of the core based on two principles: **hybridize** (a neural module
populates the graph, while the symbolic core verifies and decides) and
**ground** (a defined semantics with explicit guarantees, instead of heuristics).

> This core is a **reasoning and safeguard layer**, not a general-purpose AI.
> It reasons over explicit assertions, makes its contradictions visible,
> **suspends** judgment according to clear criteria, and **traces** every
> conclusion it reaches.

## Why v2

| v1                                                 | v2                                                                                              |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| *Ad hoc* propagation (arbitrary formulas)          | **Bounded synchronous operator**: deterministic, order-independent, with guaranteed termination |
| Perception = keywords, tightly coupled to the core | **Pluggable** perception (`RuleBased` / `LLM`) — hybridization                                  |
| Poorly formalized suspension                       | **Grounded** suspension: axiom conflict, axiom violation, ambiguity — each explicitly traced    |
| Heuristic coherence                                | **Hard** coherence (logical proof) + **soft** coherence (bounded within `[0,1]`)                |
| 3 languages (friction)                             | **Pure Python** first; Rust = later optimization of hot paths                                   |

The complete design and guarantees (proven vs. validated) are described in
**[DESIGN.md](DESIGN.md)**.

## Example

```python
from corexiom import ReasoningEngine, Assertion, Link, Relation, Status

e = ReasoningEngine()
e.add(Assertion("min_price", "never sell below 100", Status.AXIOM))
e.add(Assertion("sell80", "sell at 80", Status.BELIEF, prior=0.8, actionable=True))
e.link(Link("sell80", "min_price", Relation.CONTRADICTS, 1.0))

d = e.decide(threshold=0.5)
print(d.verdict.value)            # suspended_violates_axiom
print(d.justification.explanation)
```

## Architecture

```text
corexiom/
├── model.py      # Assertions, links, justifications (immutable, bounded)
├── engine.py     # Propagation, coherence, traced decision/suspension
└── perceive.py   # Pluggable perception: RuleBased + LLM (hybridization)
```

The neural component *proposes*, the symbolic component *verifies*: the engine
never depends on how assertions are produced, and always retains the final say
on coherence.

## Guarantees (summary)

Proven by construction: `[0,1]` bounds, axiom preservation,
determinism, order independence, and termination. Empirically validated
(property-based testing over thousands of randomly generated graphs):
convergence toward a quasi-fixed point, bounded coherence, and decision validity.
Full and honest details are provided in DESIGN.md — we do not claim to be
'unbreakable', because such a thing does not exist.

## Tests

```bash
pip install pytest hypothesis
pytest -q          # unit + property-based + adversarial tests
python demo.py     # end-to-end demonstration
```

## License

Apache 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE). Copyright 2026 Karim Benrezzag.
