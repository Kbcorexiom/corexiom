#!/usr/bin/env python3
# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""
Corexiom v2 — End-to-end demonstration.

Shows the full hybrid flow:
    text  →  perception (pluggable)  →  graph  →  reasoning  →  traced verdict

Run:  python demo.py
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
        print(f"  Target      : {d.target}  (confidence {d.confidence:.3f})")
    print(f"  Explanation : {d.justification.explanation}")
    if d.justification.assertions:
        print(f"  Proof       : {', '.join(d.justification.assertions)}")


def scenario_negotiation():
    banner("Scenario 1 — Negotiation: the proposed action violates an axiom")
    e = ReasoningEngine()
    e.add(Assertion("min_price", "never sell below 100", Status.AXIOM))
    e.add(Assertion("offer80", "customer offers 80", Status.BELIEF, prior=0.9))
    e.add(Assertion("sell80", "sell at 80", Status.BELIEF, prior=0.8, actionable=True))
    e.link(Link("offer80", "sell80", Relation.SUPPORTS, 0.6))
    e.link(Link("sell80", "min_price", Relation.CONTRADICTS, 1.0))

    res = e.propagate()
    print(f"  Coherence   : {e.coherence(res.belief):.3f}  "
          f"(converged in {res.iterations} iterations)")
    show_decision(e.decide(threshold=0.5))
    print("  → The system SUSPENDS rather than violating the axiom.")


def scenario_decision():
    banner("Scenario 2 — Grounded and traced decision")
    e = ReasoningEngine()
    e.add(Assertion("low_stock", "low stock", Status.BELIEF, prior=0.95))
    e.add(Assertion("supplier_ok", "supplier available", Status.BELIEF, prior=0.9))
    e.add(Assertion("reorder", "place order", Status.BELIEF, prior=0.4, actionable=True))
    e.link(Link("low_stock", "reorder", Relation.IMPLIES, 0.9))
    e.link(Link("supplier_ok", "reorder", Relation.SUPPORTS, 0.7))
    show_decision(e.decide(threshold=0.5))
    print("  → Decision supported by explicit evidence.")


def scenario_axiom_conflict():
    banner("Scenario 3 — Contradictory foundation: two axioms conflict")
    e = ReasoningEngine()
    e.add(Assertion("fast", "always deliver same day", Status.AXIOM))
    e.add(Assertion("careful", "never deliver same day", Status.AXIOM))
    e.link(Link("fast", "careful", Relation.CONTRADICTS, 1.0))
    show_decision(e.decide())
    print("  → No decision on a contradictory axiom foundation.")


def scenario_hybrid_perception():
    banner("Scenario 4 — Pluggable perception (the neural side would populate the graph)")
    text = ("AXIOM: never sell below the minimum price. "
            "The customer proposes a low price. "
            "Decision: accept the offer.")
    perceiver = RuleBasedPerceiver()   # interchangeable with an LLMPerceiver
    parsed = perceiver.perceive(text)
    print(f"  Text parsed into {len(parsed)} assertion(s):")
    for p in parsed:
        tag = "AXIOM" if p.status is Status.AXIOM else ("ACTION" if p.actionable else "fact")
        print(f"    [{tag:6}] {p.content}  (prior {p.prior:.2f})")
    print("  → Same flow: an LLMPerceiver would produce these assertions; the engine,")
    print("    however, remains in charge of coherence and may suspend regardless.")


if __name__ == "__main__":
    scenario_negotiation()
    scenario_decision()
    scenario_axiom_conflict()
    scenario_hybrid_perception()
    print()