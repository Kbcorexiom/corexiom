# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""
Corexiom v2 — Modèle de données.

Structures de base du noyau de raisonnement : assertions (nœuds), liens (arcs)
et objets de justification (preuves traçables). Les valeurs numériques sont
systématiquement bornées à [0, 1] dès la construction, pour qu'aucun état
invalide ne puisse exister dans le graphe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


def clamp01(x: float) -> float:
    """Borne une valeur dans [0, 1]. Garantit l'invariant fondamental du modèle."""
    if x != x:  # NaN
        raise ValueError("Valeur NaN interdite pour une croyance.")
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


class Status(Enum):
    """Statut d'une assertion."""
    AXIOM = "axiom"     # croyance verrouillée à 1.0, inviolable (contrainte dure)
    BELIEF = "belief"   # croyance révisable dans [0, 1]


class Relation(Enum):
    """Type de lien orienté entre deux assertions."""
    IMPLIES = "implies"          # a → b : si a, alors b
    SUPPORTS = "supports"        # a → b : a est une évidence (plus faible) pour b
    CONTRADICTS = "contradicts"  # a, b mutuellement exclusifs (symétrique)


@dataclass(frozen=True)
class Assertion:
    """
    Un nœud du graphe.

    - `id`      : identifiant stable (fourni par l'appelant ou généré).
    - `content` : description formelle (pas du langage naturel).
    - `status`  : AXIOM (verrouillé à 1.0) ou BELIEF (révisable).
    - `prior`   : a priori de croyance dans [0, 1] (1.0 pour un axiome).
    - `actionable` : True si l'assertion peut être choisie comme décision.

    Immuable : toute évolution de croyance se fait dans l'état du moteur, pas
    dans l'assertion elle-même (séparation données / état de calcul).
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
            raise ValueError("Une assertion doit avoir un id non vide.")

    @property
    def is_axiom(self) -> bool:
        return self.status is Status.AXIOM


@dataclass(frozen=True)
class Link:
    """
    Un arc orienté typé et pondéré entre deux assertions (par id).

    `weight ∈ [0, 1]` : force du lien. Pour CONTRADICTS, l'orientation n'a pas
    de sens (relation symétrique), mais on conserve src/dst pour l'affichage.
    """
    src: str
    dst: str
    relation: Relation
    weight: float = 1.0

    def __post_init__(self):
        object.__setattr__(self, "weight", clamp01(self.weight))
        if self.src == self.dst:
            raise ValueError("Un lien ne peut relier une assertion à elle-même.")


@dataclass(frozen=True)
class Conflict:
    """Une contradiction détectée, avec sa sévérité et sa justification."""
    a: str
    b: str
    severity: float
    hard: bool  # True si conflit entre deux axiomes (incohérence dure)


class Verdict(Enum):
    """Issue d'une décision."""
    DECIDED = "decided"
    SUSPENDED_AXIOM_CONFLICT = "suspended_axiom_conflict"
    SUSPENDED_VIOLATES_AXIOM = "suspended_violates_axiom"
    SUSPENDED_AMBIGUOUS = "suspended_ambiguous"
    INSUFFICIENT_BELIEF = "insufficient_belief"


@dataclass(frozen=True)
class Justification:
    """
    Preuve traçable accompagnant une conclusion (décision, suspension, conflit).

    - `assertions` / `links` : les éléments du graphe qui fondent la conclusion.
    - `explanation`          : résumé lisible par un humain.
    """
    assertions: List[str] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    explanation: str = ""


@dataclass(frozen=True)
class Decision:
    """Résultat complet d'une décision : verdict, cible éventuelle, preuve."""
    verdict: Verdict
    target: str | None
    confidence: float
    justification: Justification
