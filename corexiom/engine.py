# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""
Corexiom v2 — Moteur de raisonnement.

Implémente la sémantique décrite dans DESIGN.md :
- propagation de croyances par opérateur synchrone borné (déterministe,
  indépendant de l'ordre, à terminaison garantie) ;
- cohérence dure (preuve logique) et molle (masse de conflit bornée) ;
- décision avec suspension fondée et justifications traçables.

Aucun état caché : tout l'état de calcul vit dans le dictionnaire `bel`,
recalculable à tout moment depuis les assertions et les liens.
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
    """Issue d'une propagation : croyances finales et diagnostic de convergence."""
    belief: Dict[str, float]
    iterations: int
    converged: bool
    max_delta: float


class ReasoningEngine:
    """
    Noyau de raisonnement Corexiom v2.

    Paramètres de la dynamique (valeurs par défaut sûres et amorties) :
    - `gain_support`  G⁺ : poids des évidences positives.
    - `gain_conflict` G⁻ : poids des contradictions.
    - `relax`         λ  : facteur de relaxation dans (0, 1] (amortissement).
    - `epsilon`       ε  : seuil de point fixe.
    - `max_iters`        : plafond d'itérations (terminaison garantie).
    """

    def __init__(self, gain_support: float = 0.6, gain_conflict: float = 0.8,
                 relax: float = 0.5, epsilon: float = 1e-9, max_iters: int = 1000):
        if not (0.0 < relax <= 1.0):
            raise ValueError("relax doit être dans (0, 1].")
        if epsilon <= 0 or max_iters < 1:
            raise ValueError("epsilon > 0 et max_iters >= 1 requis.")
        self.gain_support = float(gain_support)
        self.gain_conflict = float(gain_conflict)
        self.relax = float(relax)
        self.epsilon = float(epsilon)
        self.max_iters = int(max_iters)

        self._assertions: Dict[str, Assertion] = {}
        self._links: List[Link] = []
        # Index : cibles -> liste de (source, poids) par catégorie d'effet.
        self._positive_in: Dict[str, List[Tuple[str, float]]] = {}
        self._conflict_in: Dict[str, List[Tuple[str, float]]] = {}

    # ----------------------------------------------------------------- #
    # Construction du graphe
    # ----------------------------------------------------------------- #
    def add(self, assertion: Assertion) -> str:
        """Ajoute (ou remplace) une assertion. Retourne son id."""
        self._assertions[assertion.id] = assertion
        self._positive_in.setdefault(assertion.id, [])
        self._conflict_in.setdefault(assertion.id, [])
        return assertion.id

    def link(self, link: Link) -> None:
        """Ajoute un lien. Les deux extrémités doivent exister."""
        if link.src not in self._assertions or link.dst not in self._assertions:
            raise KeyError("Lien vers une assertion inexistante.")
        self._links.append(link)
        if link.relation in (Relation.IMPLIES, Relation.SUPPORTS):
            self._positive_in[link.dst].append((link.src, link.weight))
        elif link.relation is Relation.CONTRADICTS:
            # Symétrique : chaque extrémité reçoit du conflit de l'autre.
            self._conflict_in[link.dst].append((link.src, link.weight))
            self._conflict_in[link.src].append((link.dst, link.weight))

    # ----------------------------------------------------------------- #
    # Propagation (opérateur synchrone borné)
    # ----------------------------------------------------------------- #
    def _initial_belief(self) -> Dict[str, float]:
        return {aid: (1.0 if a.is_axiom else a.prior)
                for aid, a in self._assertions.items()}

    def _step(self, bel: Dict[str, float]) -> Tuple[Dict[str, float], float]:
        """
        Applique une fois l'opérateur, en mode synchrone (toutes les cibles
        calculées depuis le MÊME instantané `bel`). Retourne le nouvel état et
        l'écart maximal (pour le test de convergence).
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
        Itère l'opérateur jusqu'au point fixe (écart < epsilon) ou max_iters.
        Terminaison garantie ; bornes et préservation des axiomes garanties.
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
    # Cohérence
    # ----------------------------------------------------------------- #
    def hard_incoherences(self) -> List[Conflict]:
        """
        Conflits durs, décidables exactement : un lien CONTRADICTS entre deux
        axiomes (deux propositions inviolables et mutuellement exclusives).
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
        Score de cohérence molle dans [0, 1] (borné par construction) :
        1 − (masse de conflit / somme des poids de conflit).
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
        Contradictions actives : paires CONTRADICTS dont les deux extrémités
        dépassent `active_threshold`. Les conflits durs (axiome/axiome) sont
        marqués. Liste triée par sévérité décroissante (déterministe).
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
    # Décision et suspension (fondées, traçables)
    # ----------------------------------------------------------------- #
    def _axiom_contradicting(self, target_id: str) -> Optional[Tuple[str, Link]]:
        """Retourne (axiome, lien) si un axiome contredit directement `target_id`."""
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
        Choisit l'assertion actionnable de plus haute croyance >= threshold,
        sauf suspension fondée. Toujours accompagné d'une justification.
        """
        res = self.propagate()
        bel = res.belief

        # S1 — incohérence dure : socle contradictoire.
        hard = self.hard_incoherences()
        if hard:
            c = hard[0]
            return Decision(
                verdict=Verdict.SUSPENDED_AXIOM_CONFLICT, target=None,
                confidence=0.0,
                justification=Justification(
                    assertions=[c.a, c.b],
                    explanation=(f"Suspension : les axiomes '{c.a}' et '{c.b}' "
                                 f"se contredisent. Aucune décision possible sur "
                                 f"un socle incohérent."),
                ),
            )

        # Interdiction = fait STRUCTUREL (lien CONTRADICTS vers un axiome),
        # indépendant de la valeur de croyance (que l'axiome écrase par ailleurs).
        actionable = [(aid, a) for aid, a in self._assertions.items() if a.actionable]
        forbidden = {aid for aid, _ in actionable if self._axiom_contradicting(aid)}

        # Candidates AUTORISÉES, triées par croyance décroissante (déterministe).
        allowed = sorted(
            ((aid, bel[aid]) for aid, _ in actionable if aid not in forbidden),
            key=lambda kv: (-kv[1], kv[0]),
        )
        viable = [(aid, b) for aid, b in allowed if b >= threshold]

        if viable:
            top_id, top_bel = viable[0]
            # S3 — quasi ex æquo parmi les options autorisées.
            if len(viable) >= 2 and (top_bel - viable[1][1]) < margin:
                second_id, second_bel = viable[1]
                return Decision(
                    verdict=Verdict.SUSPENDED_AMBIGUOUS, target=None,
                    confidence=top_bel,
                    justification=Justification(
                        assertions=[top_id, second_id],
                        explanation=(f"Suspension : '{top_id}' ({top_bel:.3f}) et "
                                     f"'{second_id}' ({second_bel:.3f}) sont trop "
                                     f"proches (marge < {margin:.2f})."),
                    ),
                )
            # DÉCISION : chaîne de support de la candidate retenue.
            support_links = [ln for ln in self._links
                             if ln.dst == top_id
                             and ln.relation in (Relation.IMPLIES, Relation.SUPPORTS)]
            return Decision(
                verdict=Verdict.DECIDED, target=top_id, confidence=top_bel,
                justification=Justification(
                    assertions=[top_id] + [ln.src for ln in support_links],
                    links=support_links,
                    explanation=(f"Décision : '{top_id}' (croyance {top_bel:.3f}), "
                                 f"au-dessus du seuil {threshold:.2f} et sans conflit "
                                 f"d'axiome."),
                ),
            )

        # Aucune option autorisée viable. Une action sérieuse était-elle INTERDITE ?
        # (intent = prior élevé, mais écartée par un axiome). On le dit explicitement.
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
                    explanation=(f"Suspension : l'action '{top_id}' était envisagée "
                                 f"(a priori {forbidden_serious[0][1].prior:.2f}) mais "
                                 f"violerait l'axiome '{ax_id}'."),
                ),
            )

        return Decision(
            verdict=Verdict.INSUFFICIENT_BELIEF, target=None, confidence=0.0,
            justification=Justification(
                explanation=(f"Aucune assertion actionnable autorisée n'atteint le "
                             f"seuil {threshold:.2f}. Le système ne force pas de décision."),
            ),
        )

    # ----------------------------------------------------------------- #
    # Révision de croyances (traçable)
    # ----------------------------------------------------------------- #
    def revise(self, assertion_id: str, new_prior: float) -> None:
        """
        Révise l'a priori d'une croyance (interdit sur un axiome : inviolable).
        La nouvelle croyance se recalcule à la prochaine propagation.
        """
        a = self._assertions[assertion_id]
        if a.is_axiom:
            raise ValueError(f"'{assertion_id}' est un axiome : non révisable.")
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
