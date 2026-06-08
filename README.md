<!--
Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
SPDX-License-Identifier: Apache-2.0
-->

# Corexiom v2 — Noyau de raisonnement

Refonte du noyau selon deux principes : **hybrider** (un module neuronal peuple
le graphe, le noyau symbolique vérifie et tranche) et **fonder** (une sémantique
définie, avec des garanties explicites, à la place des heuristiques).

> Ce noyau est une **couche de raisonnement et de garde-fou**, pas une IA
> généraliste. Il raisonne sur des assertions explicites, rend ses
> contradictions visibles, **suspend** son jugement sur des critères clairs, et
> **trace** chacune de ses conclusions.

## Pourquoi v2

| v1 | v2 |
|---|---|
| Propagation *ad hoc* (formules arbitraires) | Opérateur **synchrone borné** : déterministe, indépendant de l'ordre, à terminaison garantie |
| Perception = mots-clés, couplée au noyau | Perception **enfichable** (`RuleBased` / `LLM`) — hybridation |
| Suspension peu formalisée | Suspension **fondée** : conflit d'axiomes, violation d'axiome, ambiguïté — chacune tracée |
| Cohérence heuristique | Cohérence **dure** (preuve logique) + **molle** (bornée `[0,1]`) |
| 3 langages (friction) | **Python pur** d'abord ; Rust = optimisation ultérieure des chemins chauds |

La conception complète et les garanties (prouvées vs validées) sont dans
**[DESIGN.md](DESIGN.md)**.

## Exemple

```python
from corexiom import ReasoningEngine, Assertion, Link, Relation, Status

e = ReasoningEngine()
e.add(Assertion("min_price", "ne jamais vendre sous 100", Status.AXIOM))
e.add(Assertion("sell80", "vendre à 80", Status.BELIEF, prior=0.8, actionable=True))
e.link(Link("sell80", "min_price", Relation.CONTRADICTS, 1.0))

d = e.decide(threshold=0.5)
print(d.verdict.value)            # suspended_violates_axiom
print(d.justification.explanation)
```

## Architecture

```
corexiom/
├── model.py      # Assertions, liens, justifications (immuables, bornés)
├── engine.py     # Propagation, cohérence, décision/suspension tracées
└── perceive.py   # Perception enfichable : RuleBased + LLM (hybridation)
```

Le neuronal *propose*, le symbolique *vérifie* : le moteur ne dépend jamais de la
façon dont les assertions sont produites, et garde le dernier mot sur la cohérence.

## Garanties (résumé)

Prouvées par construction : bornes `[0,1]`, préservation des axiomes,
déterminisme, indépendance à l'ordre, terminaison. Validées empiriquement
(property-based testing, ~3000 graphes générés) : convergence vers un quasi-point
-fixe, bornitude de la cohérence, validité des décisions. Détail honnête dans
DESIGN.md — on ne revendique pas l'« incassable », qui n'existe pas.

## Tests

```bash
pip install pytest hypothesis
pytest -q          # unitaires + property-based + adversariaux
python demo.py     # démonstration de bout en bout
```

## Licence

Apache 2.0 — voir [LICENSE](LICENSE) et [NOTICE](NOTICE). Copyright 2026 Karim Benrezzag.
