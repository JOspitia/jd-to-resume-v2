"""
backend.domain_games._base
==========================

Base class for a domain-specific prompt game. Each game teaches the LLM how
to write a CV for one professional domain (tech, HR, psychology, ...).

Every concrete game is a plain subclass that assigns the same set of class
attributes. There is no __init__ chain here on purpose: subclasses don't need
to instantiate — they just set strings/lists/dicts at class level and they are
read via normal attribute access.

A game exposes:

    * `system_intro`             — Role definition paragraph (what the LLM is).
    * `strict_rules_block`       — Numbered rules 1–20 specific to the game.
                                   For the tech game this is the legacy v2.5
                                   prompt body verbatim. For HR/psychology it
                                   is the same skeleton adapted to the domain.
    * `narrative_patterns`       — The 4 mandatory structural patterns A/B/C/D
                                   used to break AI detection repetition.
    * `skill_taxonomy_es/en`    — Skill categories the prompt must use for the
                                   `skills` array (per language).
    * `section_labels_es/en`    — Localized section headings.

These attributes may be plain class strings / lists / dicts OR `@property`
descriptors — both work because we always read them through the descriptor
protocol by attribute access.
"""

from __future__ import annotations

from typing import Any, List


class DomainGame:
    """
    Plain base class — every concrete game sets its own class attributes.

    A single instance of each game is created lazily by `domain_games/__init__.py`
    (the GAMES registry) and reused; no per-game state is needed today.
    """

    name: str = ""
    label_es: str = ""
    label_en: str = ""
    description_es: str = ""
    description_en: str = ""

    system_intro: str = ""
    strict_rules_block: str = ""
    narrative_patterns: str = ""

    skill_taxonomy_es: List[str] = []
    skill_taxonomy_en: List[str] = []

    section_labels_es: dict = {}
    section_labels_en: dict = {}

    headline_format_es: str = ""
    headline_format_en: str = ""

    def render_system_intro(self, target_role_hint: str = "") -> str:
        """Default renderer: just return the cached system intro."""
        return self.system_intro

    def render_domain_prompt_block(self) -> str:
        """
        Compose the game-specific block (rules + patterns) that the main.py
        pipeline will splice into the prompt body. The default implementation
        concatenates `strict_rules_block` and `narrative_patterns` with a
        blank line; subclasses typically don't need to override.
        """
        parts = [self.strict_rules_block, self.narrative_patterns]
        return "\n\n".join(p.rstrip() for p in parts if p and p.strip())


__all__ = ["DomainGame"]
