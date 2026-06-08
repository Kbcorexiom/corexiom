# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""
Semantic reference cases — Layer A (specification / regression).

SCOPE AND HONESTY. This file is NOT a "ground truth". The expected verdicts
follow from the kernel's *design principle* ("suspend rather than hallucinate")
applied to deliberately generic reasoning patterns: each case is built so that
the right answer is obvious from reasoning, not from reading the code of
`decide()`. This is therefore a specification suite: it fixes the expected
behaviour and protects against regressions. Domain validation (external
sources) belongs to a distinct, clearly named Layer B.

Assertion conventions (deliberately loose, to avoid brittleness):
  - we check the VERDICT,
  - the ASSERTIONS that must appear in the justification (the "proof"),
  - confidence ONLY relative to the threshold (above / zero), never an
    exact number (which depends on G⁺/G⁻/λ and would change at the slightest
    tweak).

One pattern per verdict:
  C1 DECIDED                    — a permitted action, well supported, no conflict
  C2 INSUFFICIENT_BELIEF        — the only option is too weak to act on
  C3 SUSPENDED_AMBIGUOUS        — two permitted options in a near-tie
  C4 SUSPENDED_AXIOM_CONFLICT   — the axiom foundation is contradictory
  C5 SUSPENDED_VIOLATES_AXIOM   — the only serious action would violate an axiom
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from corexiom import (  # noqa: E402
    ReasoningEngine, Assertion, Link, Relation, Status, Verdict,
)


def _engine(asserts, links):
    e = ReasoningEngine()
    for a in asserts:
        e.add(a)
    for ln in links:
        e.link(ln)
    return e


# --------------------------------------------------------------------------- #
# C1 — DECIDED
# --------------------------------------------------------------------------- #
def test_C1_decided_supported_action():
    """
    Pattern: grounded decision.
    Expected reasoning (independent of the code) — there is ONE permitted
    action, strongly supported by solid evidence, and no axiom opposes it. A
    cautious decider MUST then decide: refusing here would be paralysis, not
    prudence. Expected verdict: DECIDED, with the evidence in the proof.
    """
    e = _engine(
        [Assertion("evidence_strong", "solid evidence", Status.BELIEF, prior=0.9),
         Assertion("action_proceed", "permitted action", Status.BELIEF, prior=0.3, actionable=True)],
        [Link("evidence_strong", "action_proceed", Relation.IMPLIES, 0.9)],
    )
    d = e.decide(threshold=0.5)
    assert d.verdict is Verdict.DECIDED
    assert d.target == "action_proceed"
    assert d.confidence >= 0.5                       # above threshold (not an exact number)
    assert {"action_proceed", "evidence_strong"} <= set(d.justification.assertions)


# --------------------------------------------------------------------------- #
# C2 — INSUFFICIENT_BELIEF
# --------------------------------------------------------------------------- #
def test_C2_insufficient_belief():
    """
    Pattern: insufficient belief.
    Expected reasoning — the only actionable option has too low a belief and
    nothing comes to support it. Forcing a decision would be unfounded. The
    system must explicitly abstain. Expected verdict: INSUFFICIENT_BELIEF,
    with no target.
    """
    e = _engine(
        [Assertion("action_weak", "poorly supported action", Status.BELIEF, prior=0.2, actionable=True)],
        [],
    )
    d = e.decide(threshold=0.6)
    assert d.verdict is Verdict.INSUFFICIENT_BELIEF
    assert d.target is None


# --------------------------------------------------------------------------- #
# C3 — SUSPENDED_AMBIGUOUS
# --------------------------------------------------------------------------- #
def test_C3_ambiguous_near_tie():
    """
    Pattern: ambiguity.
    Expected reasoning — two permitted actions are above the threshold and
    statistically indistinguishable (gap < margin). Picking one would amount
    to inventing an arbitrary preference. The system must suspend and name
    both options. Expected verdict: SUSPENDED_AMBIGUOUS, both in the proof.
    """
    e = _engine(
        [Assertion("option_A", "option A", Status.BELIEF, prior=0.80, actionable=True),
         Assertion("option_B", "option B", Status.BELIEF, prior=0.79, actionable=True)],
        [],
    )
    d = e.decide(threshold=0.5, margin=0.05)
    assert d.verdict is Verdict.SUSPENDED_AMBIGUOUS
    assert {"option_A", "option_B"} <= set(d.justification.assertions)


# --------------------------------------------------------------------------- #
# C4 — SUSPENDED_AXIOM_CONFLICT
# --------------------------------------------------------------------------- #
def test_C4_axiom_conflict():
    """
    Pattern: contradictory foundation.
    Expected reasoning — two axioms (inviolable) directly contradict each
    other. No decision can rest on a foundation that is itself contradictory:
    the problem is upstream of any action. Expected verdict:
    SUSPENDED_AXIOM_CONFLICT, with both axioms in the proof.
    """
    e = _engine(
        [Assertion("rule_1", "rule 1", Status.AXIOM),
         Assertion("rule_2", "rule 2", Status.AXIOM)],
        [Link("rule_1", "rule_2", Relation.CONTRADICTS, 1.0)],
    )
    d = e.decide()
    assert d.verdict is Verdict.SUSPENDED_AXIOM_CONFLICT
    assert {"rule_1", "rule_2"} <= set(d.justification.assertions)


# --------------------------------------------------------------------------- #
# C5 — SUSPENDED_VIOLATES_AXIOM
# --------------------------------------------------------------------------- #
def test_C5_violates_axiom():
    """
    Pattern: the only serious action would violate an axiom.
    Expected reasoning — the most credible action directly contradicts an
    inviolable rule, and no permitted alternative exists. Acting would
    violate the axiom; the system must refuse and say so (rather than
    returning a mere insufficiency). Expected verdict:
    SUSPENDED_VIOLATES_AXIOM, with the action and the axiom in the proof.
    """
    e = _engine(
        [Assertion("rule", "inviolable rule", Status.AXIOM),
         Assertion("action_fast", "fast but forbidden action", Status.BELIEF, prior=0.9, actionable=True)],
        [Link("action_fast", "rule", Relation.CONTRADICTS, 1.0)],
    )
    d = e.decide(threshold=0.5)
    assert d.verdict is Verdict.SUSPENDED_VIOLATES_AXIOM
    assert {"action_fast", "rule"} <= set(d.justification.assertions)


# --------------------------------------------------------------------------- #
# Direct execution: readable recap table
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    cases = [
        ("C1 DECIDED",
         [Assertion("evidence_strong", "e", Status.BELIEF, prior=0.9),
          Assertion("action_proceed", "a", Status.BELIEF, prior=0.3, actionable=True)],
         [Link("evidence_strong", "action_proceed", Relation.IMPLIES, 0.9)],
         dict(threshold=0.5)),
        ("C2 INSUFFICIENT",
         [Assertion("action_weak", "a", Status.BELIEF, prior=0.2, actionable=True)],
         [], dict(threshold=0.6)),
        ("C3 AMBIGUOUS",
         [Assertion("option_A", "a", Status.BELIEF, prior=0.80, actionable=True),
          Assertion("option_B", "b", Status.BELIEF, prior=0.79, actionable=True)],
         [], dict(threshold=0.5, margin=0.05)),
        ("C4 AXIOM_CONFLICT",
         [Assertion("rule_1", "r1", Status.AXIOM), Assertion("rule_2", "r2", Status.AXIOM)],
         [Link("rule_1", "rule_2", Relation.CONTRADICTS, 1.0)], dict()),
        ("C5 VIOLATES_AXIOM",
         [Assertion("rule", "r", Status.AXIOM),
          Assertion("action_fast", "a", Status.BELIEF, prior=0.9, actionable=True)],
         [Link("action_fast", "rule", Relation.CONTRADICTS, 1.0)], dict(threshold=0.5)),
    ]
    print(f"{'Case':<20}{'Observed verdict':<32}{'Confidence':<12}Proof")
    print("-" * 88)
    for name, asserts, links, kw in cases:
        d = _engine(asserts, links).decide(**kw)
        proof = ", ".join(d.justification.assertions) or "—"
        print(f"{name:<20}{d.verdict.value:<32}{d.confidence:<12.3f}{proof}")