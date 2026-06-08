# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""
Property-based and adversarial tests.

We do NOT test cherry-picked examples: we let `hypothesis` GENERATE thousands
of graphs (assertions + links) and check that the invariants declared in
DESIGN.md hold on ALL of them. This is the empirical demonstration of
robustness — the closest honest approximation to "unbreakable".

Invariants checked:
  P1  bounds       : all beliefs stay in [0, 1]
  P2  axioms       : an axiom stays at 1.0
  P3  determinism  : two runs yield the same result
  P4  order        : insertion order of nodes AND links changes nothing
  P5  termination  : propagation always halts (<= max_iters)
  P6  fixed point  : at halt, reapplying the operator moves by < epsilon
  P7  coherence    : the coherence score is in [0, 1]
  P8  decision     : decide() always returns a valid, bounded verdict
"""

import os
import sys

from hypothesis import given, settings, strategies as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from corexiom import (  # noqa: E402
    ReasoningEngine, Assertion, Link, Relation, Status, Verdict,
)
from corexiom.engine import ReasoningEngine as _Engine  # noqa: E402


# --- Strategy: generate a random graph (assertions + links) ---------------- #
N_MAX = 8

@st.composite
def random_graph(draw):
    n = draw(st.integers(min_value=1, max_value=N_MAX))
    ids = [f"n{i}" for i in range(n)]
    asserts = []
    for i in ids:
        is_ax = draw(st.booleans())
        asserts.append(Assertion(
            id=i, content=i,
            status=Status.AXIOM if is_ax else Status.BELIEF,
            prior=draw(st.floats(min_value=0.0, max_value=1.0)),
            actionable=draw(st.booleans()),
        ))
    n_links = draw(st.integers(min_value=0, max_value=n * 2))
    links = []
    for _ in range(n_links):
        s = draw(st.sampled_from(ids))
        d = draw(st.sampled_from(ids))
        if s == d:
            continue
        rel = draw(st.sampled_from(list(Relation)))
        w = draw(st.floats(min_value=0.0, max_value=1.0))
        links.append(Link(s, d, rel, w))
    return asserts, links


def build(asserts, links, **kw):
    e = ReasoningEngine(**kw)
    for a in asserts:
        e.add(a)
    for ln in links:
        e.link(ln)
    return e


@settings(max_examples=400, deadline=None)
@given(random_graph())
def test_P1_bounds(graph):
    asserts, links = graph
    bel = build(asserts, links).propagate().belief
    assert all(0.0 <= v <= 1.0 for v in bel.values())


@settings(max_examples=400, deadline=None)
@given(random_graph())
def test_P2_axioms_locked(graph):
    asserts, links = graph
    bel = build(asserts, links).propagate().belief
    for a in asserts:
        if a.is_axiom:
            assert bel[a.id] == 1.0


@settings(max_examples=300, deadline=None)
@given(random_graph())
def test_P3_determinism(graph):
    asserts, links = graph
    b1 = build(asserts, links).propagate().belief
    b2 = build(asserts, links).propagate().belief
    assert b1 == b2


@settings(max_examples=300, deadline=None)
@given(random_graph(), st.randoms(use_true_random=False))
def test_P4_order_independent(graph, rnd):
    asserts, links = graph
    shuffled_asserts = list(asserts)
    rnd.shuffle(shuffled_asserts)
    shuffled_links = list(links)
    rnd.shuffle(shuffled_links)
    b1 = build(asserts, links).propagate().belief
    # Synchronous update => result independent of insertion order, whether
    # NODES or LINKS are shuffled (floating-point summation stays stable).
    b2 = build(shuffled_asserts, shuffled_links).propagate().belief
    for k in b1:
        assert abs(b1[k] - b2[k]) < 1e-12


@settings(max_examples=400, deadline=None)
@given(random_graph())
def test_P5_termination(graph):
    asserts, links = graph
    e = build(asserts, links, max_iters=2000)
    res = e.propagate()
    assert res.iterations <= 2000  # guaranteed termination


@settings(max_examples=400, deadline=None)
@given(random_graph())
def test_P6_fixed_point_at_stop(graph):
    asserts, links = graph
    e = build(asserts, links, max_iters=5000, epsilon=1e-9)
    res = e.propagate()
    if res.converged:
        # Reapplying the operator once must (almost) not change anything.
        again, delta = e._step(res.belief)
        assert delta < 1e-6


@settings(max_examples=400, deadline=None)
@given(random_graph())
def test_P7_coherence_bounded(graph):
    asserts, links = graph
    e = build(asserts, links)
    c = e.coherence()
    assert 0.0 <= c <= 1.0


@settings(max_examples=400, deadline=None)
@given(random_graph())
def test_P8_decision_always_valid(graph):
    asserts, links = graph
    e = build(asserts, links)
    d = e.decide(threshold=0.6, margin=0.05)
    assert isinstance(d.verdict, Verdict)
    assert 0.0 <= d.confidence <= 1.0
    # If DECIDED, the target is actionable, permitted, and above threshold.
    if d.verdict is Verdict.DECIDED:
        assert d.target is not None
        assert e.assertions[d.target].actionable
        assert d.confidence >= 0.6


# --- Targeted adversarial tests -------------------------------------------- #
def test_empty_graph():
    e = ReasoningEngine()
    res = e.propagate()
    assert res.belief == {} and res.converged
    assert e.coherence() == 1.0
    assert e.decide().verdict is Verdict.INSUFFICIENT_BELIEF


def test_cycle_converges():
    # Implication cycle: must neither diverge nor loop forever.
    e = ReasoningEngine(max_iters=5000)
    for i in range(5):
        e.add(Assertion(f"c{i}", f"c{i}", Status.BELIEF, prior=0.5))
    for i in range(5):
        e.link(Link(f"c{i}", f"c{(i+1) % 5}", Relation.IMPLIES, 0.9))
    res = e.propagate()
    assert res.converged
    assert all(0.0 <= v <= 1.0 for v in res.belief.values())


def test_self_reinforcing_capped():
    # Mutual reinforcement loop: beliefs must stay <= 1.0.
    e = ReasoningEngine()
    e.add(Assertion("x", "x", Status.BELIEF, prior=0.9))
    e.add(Assertion("y", "y", Status.BELIEF, prior=0.9))
    e.link(Link("x", "y", Relation.SUPPORTS, 1.0))
    e.link(Link("y", "x", Relation.SUPPORTS, 1.0))
    bel = e.propagate().belief
    assert bel["x"] <= 1.0 and bel["y"] <= 1.0


def test_many_contradictions_stay_bounded():
    # Many contradictions: beliefs bounded, coherence in [0,1].
    e = ReasoningEngine()
    for i in range(10):
        e.add(Assertion(f"p{i}", f"p{i}", Status.BELIEF, prior=0.8))
    for i in range(10):
        for j in range(i + 1, 10):
            e.link(Link(f"p{i}", f"p{j}", Relation.CONTRADICTS, 0.5))
    bel = e.propagate().belief
    assert all(0.0 <= v <= 1.0 for v in bel.values())
    assert 0.0 <= e.coherence(bel) <= 1.0


def test_large_graph_terminates():
    e = ReasoningEngine(max_iters=5000)
    n = 200
    for i in range(n):
        e.add(Assertion(f"n{i}", f"n{i}", Status.BELIEF, prior=0.5))
    for i in range(n - 1):
        e.link(Link(f"n{i}", f"n{i+1}", Relation.IMPLIES, 0.5))
    res = e.propagate()
    assert res.converged or res.iterations == 5000
    assert all(0.0 <= v <= 1.0 for v in res.belief.values())