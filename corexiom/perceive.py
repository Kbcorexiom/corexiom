# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""
Corexiom v2 — Perception enfichable.

La perception transforme du langage naturel en assertions structurées. Elle est
**découplée** du moteur : le moteur raisonne sur des assertions, peu importe qui
les produit. C'est le point d'hybridation :

    le neuronal PEUPLE le graphe  →  le symbolique VÉRIFIE et tranche.

Deux implémentations :
- `RuleBasedPerceiver` : extraction par motifs, sans dépendance (par défaut).
- `LLMPerceiver`       : interface pour un modèle de langage (le grounding
  sérieux). Aucun appel réseau n'est codé en dur : on injecte un client.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Callable, List, Protocol

from .model import Assertion, Status


@dataclass(frozen=True)
class ParsedAssertion:
    """Assertion candidate produite par la perception, avant insertion."""
    content: str
    status: Status
    prior: float
    actionable: bool = False

    def to_assertion(self, aid: str | None = None) -> Assertion:
        return Assertion(
            id=aid or f"a-{uuid.uuid4().hex[:8]}",
            content=self.content, status=self.status,
            prior=self.prior, actionable=self.actionable,
        )


class Perceiver(Protocol):
    """Contrat de perception : du texte vers des assertions candidates."""
    def perceive(self, text: str) -> List[ParsedAssertion]: ...


class RuleBasedPerceiver:
    """
    Perception par motifs. Volontairement simple et transparente : c'est un
    point de départ sans dépendance, PAS un système de compréhension. Pour un
    grounding réel, utiliser `LLMPerceiver`.

    Conventions reconnues (insensibles à la casse) :
    - 'axiome:' / 'axiom:'      -> AXIOM (inviolable)
    - 'décision:' / 'action:'   -> BELIEF actionnable
    - 'si ... alors ...'        -> BELIEF (règle), prior modéré
    - 'peut-être' / 'hypothèse' -> BELIEF, prior faible
    - sinon                     -> BELIEF (fait), prior élevé
    """

    def perceive(self, text: str) -> List[ParsedAssertion]:
        out: List[ParsedAssertion] = []
        for raw in text.split("."):
            line = raw.strip()
            if not line:
                continue
            low = line.lower()
            if low.startswith(("axiome:", "axiom:")):
                content = line.split(":", 1)[1].strip()
                out.append(ParsedAssertion(content, Status.AXIOM, 1.0, False))
            elif low.startswith(("décision:", "decision:", "action:")):
                content = line.split(":", 1)[1].strip()
                out.append(ParsedAssertion(content, Status.BELIEF, 0.6, True))
            elif "alors" in low or low.startswith("si "):
                out.append(ParsedAssertion(line, Status.BELIEF, 0.5, False))
            elif low.startswith(("peut-être", "peut etre", "hypothèse", "hypothese")):
                out.append(ParsedAssertion(line, Status.BELIEF, 0.3, False))
            else:
                out.append(ParsedAssertion(line, Status.BELIEF, 0.7, False))
        return out


# Un client LLM est simplement une fonction : prompt -> texte de réponse.
LLMClient = Callable[[str], str]

_LLM_SYSTEM_PROMPT = """Tu extrais des assertions structurées d'un texte.
Réponds UNIQUEMENT par un tableau JSON d'objets ayant les clés :
  "content"    (str, description formelle et concise),
  "status"     ("axiom" si règle inviolable, sinon "belief"),
  "prior"      (float dans [0,1], confiance initiale),
  "actionable" (bool, true si c'est une décision/action possible).
Aucun texte hors du JSON."""


class LLMPerceiver:
    """
    Perception par modèle de langage : le neuronal peuple le graphe.

    On injecte un `client` (fonction `prompt -> réponse`). Le moteur reste
    maître de la cohérence : il vérifie et peut suspendre, quelle que soit la
    sortie du modèle. La sortie est validée et bornée avant insertion ; toute
    réponse mal formée est ignorée plutôt que de corrompre le graphe.

    Exemple d'intégration (pseudo-code) :
        def client(prompt): return mon_appel_api(prompt)
        perceiver = LLMPerceiver(client)
    """

    def __init__(self, client: LLMClient, system_prompt: str = _LLM_SYSTEM_PROMPT):
        self._client = client
        self._system_prompt = system_prompt

    def perceive(self, text: str) -> List[ParsedAssertion]:
        prompt = f"{self._system_prompt}\n\nTexte :\n{text}"
        raw = self._client(prompt)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []  # réponse non exploitable : on n'insère rien
        if not isinstance(data, list):
            return []
        out: List[ParsedAssertion] = []
        for item in data:
            if not isinstance(item, dict) or "content" not in item:
                continue
            status = (Status.AXIOM
                      if str(item.get("status", "belief")).lower() == "axiom"
                      else Status.BELIEF)
            try:
                prior = float(item.get("prior", 0.5))
            except (TypeError, ValueError):
                prior = 0.5
            out.append(ParsedAssertion(
                content=str(item["content"]).strip(),
                status=status, prior=prior,
                actionable=bool(item.get("actionable", False)),
            ))
        return out
