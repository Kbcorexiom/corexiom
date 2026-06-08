# Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
# SPDX-License-Identifier: Apache-2.0
"""Corexiom v2 — Hybrid, grounded and traceable reasoning core."""

from .model import (
    Assertion, Link, Relation, Status, Conflict, Decision, Verdict,
    Justification, clamp01,
)
from .engine import ReasoningEngine, PropagationResult
from .perceive import (
    Perceiver, RuleBasedPerceiver, LLMPerceiver, ParsedAssertion, LLMClient,
)

__all__ = [
    "Assertion", "Link", "Relation", "Status", "Conflict", "Decision",
    "Verdict", "Justification", "clamp01",
    "ReasoningEngine", "PropagationResult",
    "Perceiver", "RuleBasedPerceiver", "LLMPerceiver", "ParsedAssertion",
    "LLMClient",
]

__version__ = "2.0.0"
