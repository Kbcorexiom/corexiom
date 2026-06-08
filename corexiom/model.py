# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""
Corexiom v2 — Data model.

Core data structures of the reasoning kernel: assertions (nodes), links (edges)
and justification objects (traceable proofs). Numerical values are
systematically clamped to [0, 1] at construction time, so that no invalid
state can ever exist in the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


def clamp01(x: float) -> float:
    """Clamp a value to [0, 1]. Enforces the model's fundamental invariant."""
    if x != x:  # NaN
        raise ValueError("NaN value is not allowed for a belief.")
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


class Status(Enum):
    """Status of an assertion."""
    AXIOM = "axiom"     # belief locked at 1.0, inviolable (hard constraint)
    BELIEF = "belief"   # revisable belief in [0, 1]


class Relation(Enum):
    """Type of directed link between two assertions."""
    IMPLIES = "implies"          # a -> b: if a, then b
    SUPPORTS = "supports"        # a -> b: a is (weaker) evidence for b
    CONTRADICTS = "contradicts"  # a, b mutually exclusive (symmetric)


@dataclass(frozen=True)
class Assertion:
    """
    A node in the graph.

    - `id`         : stable identifier (provided by caller or generated).
    - `content`    : formal description (not natural language).
    - `status`     : AXIOM (locked at 1.0) or BELIEF (revisable).
    - `prior`      : prior belief in [0, 1] (1.0 for an axiom).
    - `actionable` : True if the assertion can be selected as a decision.

    Immutable: any belief evolution happens in the engine's state, not in the
    assertion itself (separation of data from computation state).
    """
    id: str
    content: str
    status: Status = Status.BELIEF
    prior: float = 0.5
    actionable: bool = False

    def __post_init__(self):
        object.__setattr__(self, "prior",
                           1.0 if self.status is Status.AXIOM else clamp01(self.prior))
        if not self.id:
            raise ValueError("An assertion must have a non-empty id.")

    @property
    def is_axiom(self) -> bool:
        return self.status is Status.AXIOM


@dataclass(frozen=True)
class Link:
    """
    A typed, weighted directed edge between two assertions (by id).

    `weight in [0, 1]`: link strength. For CONTRADICTS, orientation has no
    meaning (symmetric relation), but src/dst are kept for display purposes.
    """
    src: str
    dst: str
    relation: Relation
    weight: float = 1.0

    def __post_init__(self):
        object.__setattr__(self, "weight", clamp01(self.weight))
        if self.src == self.dst:
            raise ValueError("A link cannot connect an assertion to itself.")


@dataclass(frozen=True)
class Conflict:
    """A detected contradiction, with its severity and justification."""
    a: str
    b: str
    severity: float
    hard: bool  # True if conflict between two axioms (hard incoherence)


class Verdict(Enum):
    """Outcome of a decision."""
    DECIDED = "decided"
    SUSPENDED_AXIOM_CONFLICT = "suspended_axiom_conflict"
    SUSPENDED_VIOLATES_AXIOM = "suspended_violates_axiom"
    SUSPENDED_AMBIGUOUS = "suspended_ambiguous"
    INSUFFICIENT_BELIEF = "insufficient_belief"


@dataclass(frozen=True)
class Justification:
    """
    Traceable proof attached to a conclusion (decision, suspension, conflict).

    - `assertions` / `links` : graph elements grounding the conclusion.
    - `explanation`          : human-readable summary.
    """
    assertions: List[str] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    explanation: str = ""


@dataclass(frozen=True)
class Decision:
    """Full decision result: verdict, optional target, proof."""
    verdict: Verdict
    target: str | None
    confidence: float
    justification: Justification