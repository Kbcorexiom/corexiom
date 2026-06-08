# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""
Corexiom v2 — Pluggable perception.

Perception turns natural language into structured assertions. It is
**decoupled** from the engine: the engine reasons over assertions regardless
of who produces them. This is the hybridization point:

    the neural side POPULATES the graph  ->  the symbolic side VERIFIES and decides.

Two implementations:
- `RuleBasedPerceiver`: pattern-based extraction, no dependencies (default).
- `LLMPerceiver`      : interface for a language model (serious grounding).
  No network call is hard-coded: a client is injected.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Callable, List, Protocol

from .model import Assertion, Status


@dataclass(frozen=True)
class ParsedAssertion:
    """Candidate assertion produced by perception, before insertion."""
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
    """Perception contract: from text to candidate assertions."""
    def perceive(self, text: str) -> List[ParsedAssertion]: ...


class RuleBasedPerceiver:
    """
    Pattern-based perception. Deliberately simple and transparent: a starting
    point with no dependencies, NOT an understanding system. For real
    grounding, use `LLMPerceiver`.

    Recognized conventions (case-insensitive, English and French supported):
    - 'axiom:' / 'axiome:'                            -> AXIOM (inviolable)
    - 'decision:' / 'action:' / 'décision:'           -> BELIEF actionable
    - 'if ... then ...' / 'si ... alors ...'          -> BELIEF (rule), moderate prior
    - 'maybe' / 'perhaps' / 'hypothesis' / 'peut-être' / 'hypothèse'
                                                      -> BELIEF, low prior
    - otherwise                                       -> BELIEF (fact), high prior
    """

    def perceive(self, text: str) -> List[ParsedAssertion]:
        out: List[ParsedAssertion] = []
        for raw in text.split("."):
            line = raw.strip()
            if not line:
                continue
            low = line.lower()
            if low.startswith(("axiom:", "axiome:")):
                content = line.split(":", 1)[1].strip()
                out.append(ParsedAssertion(content, Status.AXIOM, 1.0, False))
            elif low.startswith(("decision:", "action:", "décision:")):
                content = line.split(":", 1)[1].strip()
                out.append(ParsedAssertion(content, Status.BELIEF, 0.6, True))
            elif (" then " in low or "alors" in low
                  or low.startswith(("if ", "si "))):
                out.append(ParsedAssertion(line, Status.BELIEF, 0.5, False))
            elif low.startswith(("maybe", "perhaps", "hypothesis",
                                 "peut-être", "peut etre",
                                 "hypothèse", "hypothese")):
                out.append(ParsedAssertion(line, Status.BELIEF, 0.3, False))
            else:
                out.append(ParsedAssertion(line, Status.BELIEF, 0.7, False))
        return out


# An LLM client is simply a function: prompt -> response text.
LLMClient = Callable[[str], str]

_LLM_SYSTEM_PROMPT = """You extract structured assertions from a text.
Reply ONLY with a JSON array of objects with the following keys:
  "content"    (str, formal and concise description),
  "status"     ("axiom" if inviolable rule, otherwise "belief"),
  "prior"      (float in [0,1], initial confidence),
  "actionable" (bool, true if this is a possible decision/action).
No text outside the JSON."""


class LLMPerceiver:
    """
    Perception via a language model: the neural side populates the graph.

    A `client` (a `prompt -> response` function) is injected. The engine
    remains in charge of coherence: it verifies and may suspend, regardless
    of the model's output. The output is validated and clamped before
    insertion; any malformed response is ignored rather than corrupting the
    graph.

    Integration example (pseudo-code):
        def client(prompt): return my_api_call(prompt)
        perceiver = LLMPerceiver(client)
    """

    def __init__(self, client: LLMClient, system_prompt: str = _LLM_SYSTEM_PROMPT):
        self._client = client
        self._system_prompt = system_prompt

    def perceive(self, text: str) -> List[ParsedAssertion]:
        prompt = f"{self._system_prompt}\n\nText:\n{text}"
        raw = self._client(prompt)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []  # unusable response: nothing is inserted
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