# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""
Corexiom v2 — Reasoning engine.

Implements the semantics described in DESIGN.md:
- belief propagation via a bounded synchronous operator (deterministic,
  order-independent, with guaranteed termination);
- hard coherence (logical proof) and soft coherence (bounded conflict mass);
- decision with grounded suspension and traceable justifications.

No hidden state: the entire computation state lives in the `bel` dictionary,
recomputable at any time from the assertions and links.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .model import (
    Assertion, Link, Relation, Status, Conflict, Decision, Verdict,
    Justification, clamp01,
)


@dataclass(frozen=True)
class PropagationResult:
    """Outcome of a propagation: final beliefs and convergence diagnostic."""
    belief: Dict[str, float]
    iterations: int
    converged: bool
    max_delta: float


class ReasoningEngine:
    """
    Corexiom v2 reasoning kernel.

    Dynamics parameters (safe and damped defaults):
    - `gain_support`  G+ : weight of positive evidence.
    - `gain_conflict` G- : weight of contradictions.
    - `relax`         λ  : relaxation factor in (0, 1] (damping).
    - `epsilon`       ε  : fixed-point threshold.
    - `max_iters`        : iteration cap (guaranteed termination).
    """

    def __init__(self, gain_support: float = 0.6, gain_conflict: float = 0.8,
                 relax: float = 0.5, epsilon: float = 1e-9, max_iters: int = 1000):
        if not (0.0 < relax <= 1.0):
            raise ValueError("relax must be in (0, 1].")
        if epsilon <= 0 or max_iters < 1:
            raise ValueError("epsilon > 0 and max_iters >= 1 required.")
        self.gain_support = float(gain_support)
        self.gain_conflict = float(gain_conflict)
        self.relax = float(relax)
        self.epsilon = float(epsilon)
        self.max_iters = int(max_iters)

        self._assertions: Dict[str, Assertion] = {}
        self._links: List[Link] = []
        # Index: targets -> list of (source, weight) by effect category.
        self._positive_in: Dict[str, List[Tuple[str, float]]] = {}
        self._conflict_in: Dict[str, List[Tuple[str, float]]] = {}

    # ----------------------------------------------------------------- #
    # Graph construction
    # ----------------------------------------------------------------- #
    def add(self, assertion: Assertion) -> str:
        """Add (or replace) an assertion. Returns its id."""
        self._assertions[assertion.id] = assertion
        self._positive_in.setdefault(assertion.id, [])
        self._conflict_in.setdefault(assertion.id, [])
        return assertion.id

    def link(self, link: Link) -> None:
        """Add a link. Both endpoints must exist."""
        if link.src not in self._assertions or link.dst not in self._assertions:
            raise KeyError("Link to a non-existent assertion.")
        self._links.append(link)
        if link.relation in (Relation.IMPLIES, Relation.SUPPORTS):
            self._positive_in[link.dst].append((link.src, link.weight))
        elif link.relation is Relation.CONTRADICTS:
            # Symmetric: each endpoint receives conflict from the other.
            self._conflict_in[link.dst].append((link.src, link.weight))
            self._conflict_in[link.src].append((link.dst, link.weight))

    # ----------------------------------------------------------------- #
    # Propagation (bounded synchronous operator)
    # ----------------------------------------------------------------- #
    def _initial_belief(self) -> Dict[str, float]:
        return {aid: (1.0 if a.is_axiom else a.prior)
                for aid, a in self._assertions.items()}

    def _step(self, bel: Dict[str, float]) -> Tuple[Dict[str, float], float]:
        """
        Apply the operator once, in synchronous mode (all targets computed
        from the SAME snapshot `bel`). Returns the new state and the maximum
        delta (for the convergence test).
        """
        new = dict(bel)
        max_delta = 0.0
        for aid, a in self._assertions.items():
            if a.is_axiom:
                new[aid] = 1.0
                continue
            support = sum(bel[s] * w for s, w in self._positive_in[aid])
            conflict = sum(bel[c] * w for c, w in self._conflict_in[aid])
            target = clamp01(a.prior
                             + self.gain_support * support
                             - self.gain_conflict * conflict)
            updated = (1.0 - self.relax) * bel[aid] + self.relax * target
            updated = clamp01(updated)
            new[aid] = updated
            d = abs(updated - bel[aid])
            if d > max_delta:
                max_delta = d
        return new, max_delta

    def propagate(self) -> PropagationResult:
        """
        Iterate the operator until a fixed point (delta < epsilon) or
        max_iters. Termination is guaranteed; bounds and axiom preservation
        are guaranteed.
        """
        bel = self._initial_belief()
        iterations = 0
        max_delta = 0.0
        converged = False
        for _ in range(self.max_iters):
            bel, max_delta = self._step(bel)
            iterations += 1
            if max_delta < self.epsilon:
                converged = True
                break
        return PropagationResult(belief=bel, iterations=iterations,
                                 converged=converged, max_delta=max_delta)

    # ----------------------------------------------------------------- #
    # Coherence
    # ----------------------------------------------------------------- #
    def hard_incoherences(self) -> List[Conflict]:
        """
        Hard, exactly decidable conflicts: a CONTRADICTS link between two
        axioms (two inviolable, mutually exclusive propositions).
        """
        out: List[Conflict] = []
        seen = set()
        for ln in self._links:
            if ln.relation is not Relation.CONTRADICTS:
                continue
            a, b = self._assertions[ln.src], self._assertions[ln.dst]
            if a.is_axiom and b.is_axiom:
                key = frozenset((ln.src, ln.dst))
                if key in seen:
                    continue
                seen.add(key)
                out.append(Conflict(a=ln.src, b=ln.dst, severity=1.0, hard=True))
        return out

    def coherence(self, belief: Optional[Dict[str, float]] = None) -> float:
        """
        Soft coherence score in [0, 1] (bounded by construction):
        1 - (conflict mass / sum of conflict weights).
        """
        bel = belief if belief is not None else self.propagate().belief
        mass = 0.0
        wsum = 0.0
        seen = set()
        for ln in self._links:
            if ln.relation is not Relation.CONTRADICTS:
                continue
            key = frozenset((ln.src, ln.dst))
            if key in seen:
                continue
            seen.add(key)
            mass += bel[ln.src] * bel[ln.dst] * ln.weight
            wsum += ln.weight
        if wsum == 0.0:
            return 1.0
        return 1.0 - clamp01(mass / wsum)

    def detect_conflicts(self, belief: Optional[Dict[str, float]] = None,
                         active_threshold: float = 0.5) -> List[Conflict]:
        """
        Active contradictions: CONTRADICTS pairs where both endpoints exceed
        `active_threshold`. Hard conflicts (axiom/axiom) are flagged. List
        sorted by decreasing severity (deterministic).
        """
        bel = belief if belief is not None else self.propagate().belief
        out: List[Conflict] = []
        seen = set()
        for ln in self._links:
            if ln.relation is not Relation.CONTRADICTS:
                continue
            key = frozenset((ln.src, ln.dst))
            if key in seen:
                continue
            seen.add(key)
            pa, pb = bel[ln.src], bel[ln.dst]
            if pa >= active_threshold and pb >= active_threshold:
                a, b = self._assertions[ln.src], self._assertions[ln.dst]
                out.append(Conflict(a=ln.src, b=ln.dst,
                                    severity=pa * pb * ln.weight,
                                    hard=a.is_axiom and b.is_axiom))
        out.sort(key=lambda c: (-c.severity, c.a, c.b))
        return out

    # ----------------------------------------------------------------- #
    # Decision and suspension (grounded, traceable)
    # ----------------------------------------------------------------- #
    def _axiom_contradicting(self, target_id: str) -> Optional[Tuple[str, Link]]:
        """Return (axiom, link) if an axiom directly contradicts `target_id`."""
        for ln in self._links:
            if ln.relation is not Relation.CONTRADICTS:
                continue
            if ln.src == target_id and self._assertions[ln.dst].is_axiom:
                return ln.dst, ln
            if ln.dst == target_id and self._assertions[ln.src].is_axiom:
                return ln.src, ln
        return None

    def decide(self, threshold: float = 0.6, margin: float = 0.05) -> Decision:
        """
        Select the actionable assertion with the highest belief >= threshold,
        unless suspended on grounded criteria. Always accompanied by a
        justification.
        """
        res = self.propagate()
        bel = res.belief

        # S1 - hard incoherence: contradictory foundation.
        hard = self.hard_incoherences()
        if hard:
            c = hard[0]
            return Decision(
                verdict=Verdict.SUSPENDED_AXIOM_CONFLICT, target=None,
                confidence=0.0,
                justification=Justification(
                    assertions=[c.a, c.b],
                    explanation=(f"Suspended: axioms '{c.a}' and '{c.b}' "
                                 f"contradict each other. No decision is possible "
                                 f"on a contradictory foundation."),
                ),
            )

        # Prohibition = STRUCTURAL fact (CONTRADICTS link to an axiom),
        # independent of belief value (which the axiom overrides anyway).
        actionable = [(aid, a) for aid, a in self._assertions.items() if a.actionable]
        forbidden = {aid for aid, _ in actionable if self._axiom_contradicting(aid)}

        # PERMITTED candidates, sorted by decreasing belief (deterministic).
        allowed = sorted(
            ((aid, bel[aid]) for aid, _ in actionable if aid not in forbidden),
            key=lambda kv: (-kv[1], kv[0]),
        )
        viable = [(aid, b) for aid, b in allowed if b >= threshold]

        if viable:
            top_id, top_bel = viable[0]
            # S3 - near-tie among permitted options.
            if len(viable) >= 2 and (top_bel - viable[1][1]) < margin:
                second_id, second_bel = viable[1]
                return Decision(
                    verdict=Verdict.SUSPENDED_AMBIGUOUS, target=None,
                    confidence=top_bel,
                    justification=Justification(
                        assertions=[top_id, second_id],
                        explanation=(f"Suspended: '{top_id}' ({top_bel:.3f}) and "
                                     f"'{second_id}' ({second_bel:.3f}) are too "
                                     f"close (margin < {margin:.2f})."),
                    ),
                )
            # DECISION: support chain of the selected candidate.
            support_links = [ln for ln in self._links
                             if ln.dst == top_id
                             and ln.relation in (Relation.IMPLIES, Relation.SUPPORTS)]
            return Decision(
                verdict=Verdict.DECIDED, target=top_id, confidence=top_bel,
                justification=Justification(
                    assertions=[top_id] + [ln.src for ln in support_links],
                    links=support_links,
                    explanation=(f"Decision: '{top_id}' (belief {top_bel:.3f}), "
                                 f"above threshold {threshold:.2f} and with no "
                                 f"axiom conflict."),
                ),
            )

        # No permitted viable option. Was a serious action FORBIDDEN?
        # (intent = high prior, but ruled out by an axiom). State it explicitly.
        forbidden_serious = sorted(
            ((aid, a) for aid, a in actionable
             if aid in forbidden and a.prior >= threshold),
            key=lambda kv: (-kv[1].prior, kv[0]),
        )
        if forbidden_serious:
            top_id = forbidden_serious[0][0]
            ax_id, ln = self._axiom_contradicting(top_id)
            return Decision(
                verdict=Verdict.SUSPENDED_VIOLATES_AXIOM, target=None,
                confidence=0.0,
                justification=Justification(
                    assertions=[top_id, ax_id], links=[ln],
                    explanation=(f"Suspended: the action '{top_id}' was considered "
                                 f"(prior {forbidden_serious[0][1].prior:.2f}) but "
                                 f"would violate the axiom '{ax_id}'."),
                ),
            )

        return Decision(
            verdict=Verdict.INSUFFICIENT_BELIEF, target=None, confidence=0.0,
            justification=Justification(
                explanation=(f"No permitted actionable assertion reaches threshold "
                             f"{threshold:.2f}. The system does not force a decision."),
            ),
        )

    # ----------------------------------------------------------------- #
    # Belief revision (traceable)
    # ----------------------------------------------------------------- #
    def revise(self, assertion_id: str, new_prior: float) -> None:
        """
        Revise the prior of a belief (forbidden on an axiom: inviolable).
        The new belief is recomputed at the next propagation.
        """
        a = self._assertions[assertion_id]
        if a.is_axiom:
            raise ValueError(f"'{assertion_id}' is an axiom: not revisable.")
        self._assertions[assertion_id] = Assertion(
            id=a.id, content=a.content, status=a.status,
            prior=clamp01(new_prior), actionable=a.actionable,
        )

    # ----------------------------------------------------------------- #
    # Introspection
    # ----------------------------------------------------------------- #
    @property
    def assertions(self) -> Dict[str, Assertion]:
        return dict(self._assertions)

    @property
    def links(self) -> List[Link]:
        return list(self._links)