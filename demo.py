#!/usr/bin/env python3
# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""
Corexiom v2 — Démonstration de bout en bout.

Montre le flux hybride complet :
    texte  →  perception (enfichable)  →  graphe  →  raisonnement  →  verdict tracé

Lancement :  python demo.py
"""

from corexiom import (
    ReasoningEngine, Assertion, Link, Relation, Status, Verdict,
    RuleBasedPerceiver,
)


def banner(t):
    print("\n" + "=" * 68 + f"\n {t}\n" + "=" * 68)


def show_decision(d):
    print(f"  Verdict     : {d.verdict.value}")
    if d.target:
        print(f"  Cible       : {d.target}  (confiance {d.confidence:.3f})")
    print(f"  Explication : {d.justification.explanation}")
    if d.justification.assertions:
        print(f"  Preuve      : {', '.join(d.justification.assertions)}")


def scenario_negotiation():
    banner("Scénario 1 — Négociation : l'action proposée viole un axiome")
    e = ReasoningEngine()
    e.add(Assertion("min_price", "ne jamais vendre sous 100", Status.AXIOM))
    e.add(Assertion("offer80", "le client offre 80", Status.BELIEF, prior=0.9))
    e.add(Assertion("sell80", "vendre à 80", Status.BELIEF, prior=0.8, actionable=True))
    e.link(Link("offer80", "sell80", Relation.SUPPORTS, 0.6))
    e.link(Link("sell80", "min_price", Relation.CONTRADICTS, 1.0))

    res = e.propagate()
    print(f"  Cohérence   : {e.coherence(res.belief):.3f}  "
          f"(convergé en {res.iterations} itérations)")
    show_decision(e.decide(threshold=0.5))
    print("  → Le système SUSPEND plutôt que de violer l'axiome.")


def scenario_decision():
    banner("Scénario 2 — Décision fondée et tracée")
    e = ReasoningEngine()
    e.add(Assertion("low_stock", "stock faible", Status.BELIEF, prior=0.95))
    e.add(Assertion("supplier_ok", "fournisseur disponible", Status.BELIEF, prior=0.9))
    e.add(Assertion("reorder", "passer commande", Status.BELIEF, prior=0.4, actionable=True))
    e.link(Link("low_stock", "reorder", Relation.IMPLIES, 0.9))
    e.link(Link("supplier_ok", "reorder", Relation.SUPPORTS, 0.7))
    show_decision(e.decide(threshold=0.5))
    print("  → Décision soutenue par des évidences explicites.")


def scenario_axiom_conflict():
    banner("Scénario 3 — Socle incohérent : deux axiomes se contredisent")
    e = ReasoningEngine()
    e.add(Assertion("fast", "toujours livrer le jour même", Status.AXIOM))
    e.add(Assertion("careful", "ne jamais livrer le jour même", Status.AXIOM))
    e.link(Link("fast", "careful", Relation.CONTRADICTS, 1.0))
    show_decision(e.decide())
    print("  → Aucune décision sur un socle d'axiomes contradictoire.")


def scenario_hybrid_perception():
    banner("Scénario 4 — Perception enfichable (le neuronal peuplerait le graphe)")
    text = ("AXIOME: ne jamais vendre sous le prix minimum. "
            "Le client propose un prix bas. "
            "Décision: accepter l'offre.")
    perceiver = RuleBasedPerceiver()   # remplaçable par un LLMPerceiver
    parsed = perceiver.perceive(text)
    print(f"  Texte perçu en {len(parsed)} assertion(s) :")
    for p in parsed:
        tag = "AXIOME" if p.status is Status.AXIOM else ("ACTION" if p.actionable else "fait")
        print(f"    [{tag:6}] {p.content}  (prior {p.prior:.2f})")
    print("  → Même flux : un LLMPerceiver produirait ces assertions ; le moteur, lui,")
    print("    reste maître de la cohérence et peut suspendre quoi qu'il arrive.")


if __name__ == "__main__":
    scenario_negotiation()
    scenario_decision()
    scenario_axiom_conflict()
    scenario_hybrid_perception()
    print()
