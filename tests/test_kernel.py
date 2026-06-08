# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""Tests unitaires : décision, suspension, cohérence, révision, perception."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from corexiom import (  # noqa: E402
    ReasoningEngine, Assertion, Link, Relation, Status, Verdict,
    RuleBasedPerceiver, LLMPerceiver,
)


def test_decision_founded():
    e = ReasoningEngine()
    e.add(Assertion("ev", "stock faible", Status.BELIEF, prior=0.9))
    e.add(Assertion("act", "commander", Status.BELIEF, prior=0.5, actionable=True))
    e.link(Link("ev", "act", Relation.IMPLIES, 0.9))
    d = e.decide(threshold=0.5)
    assert d.verdict is Verdict.DECIDED and d.target == "act"
    assert "act" in d.justification.assertions  # justification non vide


def test_suspend_violates_axiom():
    e = ReasoningEngine()
    e.add(Assertion("ax", "ne jamais vendre sous 100", Status.AXIOM))
    e.add(Assertion("act", "vendre a 80", Status.BELIEF, prior=0.8, actionable=True))
    e.link(Link("act", "ax", Relation.CONTRADICTS, 1.0))
    d = e.decide(threshold=0.5)
    assert d.verdict is Verdict.SUSPENDED_VIOLATES_AXIOM
    assert "ax" in d.justification.assertions


def test_suspend_axiom_conflict():
    e = ReasoningEngine()
    e.add(Assertion("a", "toujours X", Status.AXIOM))
    e.add(Assertion("b", "jamais X", Status.AXIOM))
    e.link(Link("a", "b", Relation.CONTRADICTS, 1.0))
    assert e.hard_incoherences()
    assert e.decide().verdict is Verdict.SUSPENDED_AXIOM_CONFLICT


def test_suspend_ambiguous():
    e = ReasoningEngine()
    e.add(Assertion("A", "A", Status.BELIEF, prior=0.80, actionable=True))
    e.add(Assertion("B", "B", Status.BELIEF, prior=0.79, actionable=True))
    assert e.decide(threshold=0.5, margin=0.05).verdict is Verdict.SUSPENDED_AMBIGUOUS


def test_allowed_preferred_over_forbidden():
    e = ReasoningEngine()
    e.add(Assertion("ax", "ne jamais vendre sous 100", Status.AXIOM))
    e.add(Assertion("bad", "vendre a 80", Status.BELIEF, prior=0.9, actionable=True))
    e.add(Assertion("good", "vendre a 120", Status.BELIEF, prior=0.85, actionable=True))
    e.link(Link("bad", "ax", Relation.CONTRADICTS, 1.0))
    d = e.decide(threshold=0.5)
    assert d.verdict is Verdict.DECIDED and d.target == "good"


def test_insufficient_belief():
    e = ReasoningEngine()
    e.add(Assertion("act", "agir", Status.BELIEF, prior=0.2, actionable=True))
    assert e.decide(threshold=0.6).verdict is Verdict.INSUFFICIENT_BELIEF


def test_coherence_bounds_and_value():
    e = ReasoningEngine()
    e.add(Assertion("a", "a", Status.BELIEF, prior=1.0))
    e.add(Assertion("b", "b", Status.BELIEF, prior=1.0))
    e.link(Link("a", "b", Relation.CONTRADICTS, 1.0))
    c = e.coherence()
    assert 0.0 <= c <= 1.0
    # deux croyances fortes en contradiction -> cohérence dégradée
    assert c < 1.0


def test_no_contradiction_full_coherence():
    e = ReasoningEngine()
    e.add(Assertion("a", "a", Status.BELIEF, prior=0.9))
    assert e.coherence() == 1.0


def test_revision_changes_outcome():
    e = ReasoningEngine()
    e.add(Assertion("act", "agir", Status.BELIEF, prior=0.2, actionable=True))
    assert e.decide(threshold=0.6).verdict is Verdict.INSUFFICIENT_BELIEF
    e.revise("act", 0.95)
    assert e.decide(threshold=0.6).verdict is Verdict.DECIDED


def test_axiom_not_revisable():
    e = ReasoningEngine()
    e.add(Assertion("ax", "regle", Status.AXIOM))
    with pytest.raises(ValueError):
        e.revise("ax", 0.5)


def test_model_rejects_invalid():
    with pytest.raises(ValueError):
        Assertion("", "vide")  # id vide
    with pytest.raises(ValueError):
        Link("x", "x", Relation.IMPLIES)  # boucle sur soi
    with pytest.raises(ValueError):
        Assertion("a", "x", prior=float("nan"))  # NaN interdit


def test_link_to_missing_assertion():
    e = ReasoningEngine()
    e.add(Assertion("a", "a"))
    with pytest.raises(KeyError):
        e.link(Link("a", "ghost", Relation.IMPLIES))


# --- Perception ------------------------------------------------------------ #
def test_rule_based_perceiver():
    p = RuleBasedPerceiver()
    items = p.perceive("AXIOME: ne jamais mentir. Decision: accepter. le prix est 100")
    kinds = {i.content: i for i in items}
    assert any(i.status is Status.AXIOM for i in items)
    assert any(i.actionable for i in items)


def test_llm_perceiver_parses_json():
    def fake_client(prompt):
        return ('[{"content":"regle","status":"axiom","prior":1.0,"actionable":false},'
                '{"content":"agir","status":"belief","prior":0.7,"actionable":true}]')
    p = LLMPerceiver(fake_client)
    items = p.perceive("peu importe")
    assert len(items) == 2
    assert items[0].status is Status.AXIOM
    assert items[1].actionable


def test_llm_perceiver_rejects_garbage():
    # Une réponse non-JSON ne doit RIEN insérer (pas de corruption du graphe).
    p = LLMPerceiver(lambda prompt: "désolé je ne peux pas")
    assert p.perceive("x") == []
