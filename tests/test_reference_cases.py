# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""
Cas de référence sémantique — Couche A (spécification / régression).

PORTÉE ET HONNÊTETÉ. Ce fichier n'est PAS une « vérité terrain ». Les verdicts
attendus découlent du *principe de conception* du noyau (« suspendre plutôt
qu'halluciner ») sur des motifs de raisonnement volontairement génériques :
chaque cas est construit pour que la bonne réponse soit évidente par le
raisonnement, pas par la lecture du code de `decide()`. C'est donc une suite de
spécification : elle fixe le comportement attendu et protège contre les
régressions. La validation métier (sources externes) relève d'une couche B
distincte et clairement nommée.

Conventions d'assertion (volontairement souples, pour ne pas être fragiles) :
  - on vérifie le VERDICT,
  - les ASSERTIONS qui doivent figurer dans la justification (la « preuve »),
  - la confiance UNIQUEMENT relativement au seuil (au-dessus / nulle), jamais
    un nombre exact (qui dépend de G⁺/G⁻/λ et changerait au moindre réglage).

Un motif par verdict :
  C1 DECIDED                    — une action permise, bien soutenue, sans conflit
  C2 INSUFFICIENT_BELIEF        — la seule option est trop faible pour agir
  C3 SUSPENDED_AMBIGUOUS        — deux options permises quasi ex æquo
  C4 SUSPENDED_AXIOM_CONFLICT   — le socle d'axiomes est contradictoire
  C5 SUSPENDED_VIOLATES_AXIOM   — la seule action sérieuse violerait un axiome
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
    Motif : décision fondée.
    Raisonnement attendu (indépendant du code) — il existe UNE action permise,
    fortement soutenue par une évidence solide, et aucun axiome ne s'y oppose.
    Un décideur prudent DOIT alors trancher : refuser ici serait de la paralysie,
    pas de la prudence. Verdict attendu : DECIDED, avec l'évidence dans la preuve.
    """
    e = _engine(
        [Assertion("evidence_strong", "évidence solide", Status.BELIEF, prior=0.9),
         Assertion("action_proceed", "action permise", Status.BELIEF, prior=0.3, actionable=True)],
        [Link("evidence_strong", "action_proceed", Relation.IMPLIES, 0.9)],
    )
    d = e.decide(threshold=0.5)
    assert d.verdict is Verdict.DECIDED
    assert d.target == "action_proceed"
    assert d.confidence >= 0.5                       # au-dessus du seuil (pas un nombre exact)
    assert {"action_proceed", "evidence_strong"} <= set(d.justification.assertions)


# --------------------------------------------------------------------------- #
# C2 — INSUFFICIENT_BELIEF
# --------------------------------------------------------------------------- #
def test_C2_insufficient_belief():
    """
    Motif : insuffisance de croyance.
    Raisonnement attendu — la seule option actionnable a une croyance trop faible
    et rien ne vient l'étayer. Forcer une décision serait infondé. Le système doit
    s'abstenir explicitement. Verdict attendu : INSUFFICIENT_BELIEF, sans cible.
    """
    e = _engine(
        [Assertion("action_weak", "action peu étayée", Status.BELIEF, prior=0.2, actionable=True)],
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
    Motif : ambiguïté.
    Raisonnement attendu — deux actions permises sont au-dessus du seuil et
    statistiquement indiscernables (écart < marge). Trancher reviendrait à
    inventer une préférence arbitraire. Le système doit suspendre et nommer les
    deux options. Verdict attendu : SUSPENDED_AMBIGUOUS, les deux dans la preuve.
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
    Motif : socle incohérent.
    Raisonnement attendu — deux axiomes (inviolables) se contredisent directement.
    Aucune décision ne peut reposer sur un fondement lui-même contradictoire : le
    problème est en amont de toute action. Verdict attendu : SUSPENDED_AXIOM_CONFLICT,
    les deux axiomes dans la preuve.
    """
    e = _engine(
        [Assertion("rule_1", "règle 1", Status.AXIOM),
         Assertion("rule_2", "règle 2", Status.AXIOM)],
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
    Motif : la seule action sérieuse violerait un axiome.
    Raisonnement attendu — l'action la plus crédible est en contradiction directe
    avec une règle inviolable, et il n'existe aucune alternative permise. Agir
    violerait l'axiome ; le système doit refuser et le dire (plutôt que de
    renvoyer une simple insuffisance). Verdict attendu : SUSPENDED_VIOLATES_AXIOM,
    avec l'action et l'axiome dans la preuve.
    """
    e = _engine(
        [Assertion("rule", "règle inviolable", Status.AXIOM),
         Assertion("action_fast", "action rapide mais interdite", Status.BELIEF, prior=0.9, actionable=True)],
        [Link("action_fast", "rule", Relation.CONTRADICTS, 1.0)],
    )
    d = e.decide(threshold=0.5)
    assert d.verdict is Verdict.SUSPENDED_VIOLATES_AXIOM
    assert {"action_fast", "rule"} <= set(d.justification.assertions)


# --------------------------------------------------------------------------- #
# Exécution directe : tableau récapitulatif lisible
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
    print(f"{'Cas':<20}{'Verdict obtenu':<32}{'Confiance':<10}Preuve")
    print("-" * 88)
    for name, asserts, links, kw in cases:
        d = _engine(asserts, links).decide(**kw)
        preuve = ", ".join(d.justification.assertions) or "—"
        print(f"{name:<20}{d.verdict.value:<32}{d.confidence:<10.3f}{preuve}")
