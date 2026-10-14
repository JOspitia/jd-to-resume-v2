"""
backend.domain_games
====================

Prompt game registry — multi-domain resume tailoring.

A "game" (игра / игла) is a coherent bundle of prompt instructions that teaches the
LLM how to write a CV for one professional domain. Currently supported games:

    * "tech"          — Software engineers, developers, data/ML engineers.
    * "hr_recruiting" — Analysts and managers in talent acquisition / selection.
    * "psychology"    — Psychologists (organizational, clinical, educational).

The tech game is the original prompt body of `main.py` v2.5, preserved verbatim
and split into a renderable structure. HR and Psychology follow the same
20-rule skeleton, but with domain-specific action verbs, narrative patterns,
skill taxonomy and section labels.

Public API:
    DEFAULT_GAME      -> str          # "tech"
    GAMES             -> dict[str, DomainGame]
    get_game(name)    -> DomainGame   # fall back to Tech if name is unknown

Future games (e.g. "marketing", "design", "finance") only need to subclass
DomainGame and register here.
"""

from __future__ import annotations

from ._base import DomainGame
from .tech import TechGame
from .hr_recruiting import HrRecruitingGame
from .psychology import PsychologyGame


DEFAULT_GAME = "tech"

# Registry holds INSTANCES (one per game), not classes, so attribute access
# (including @property descriptors) returns values, not descriptors.
GAMES: dict[str, DomainGame] = {
    TechGame.name: TechGame(),
    HrRecruitingGame.name: HrRecruitingGame(),
    PsychologyGame.name: PsychologyGame(),
}


def get_game(name: str | None = None) -> DomainGame:
    """
    Resolve a game by name. Falls back to `DEFAULT_GAME` (tech) for unknown or
    empty values, so legacy callers that don't pass a game keep working.
    """
    if not name:
        return GAMES[DEFAULT_GAME]
    return GAMES.get(name, GAMES[DEFAULT_GAME])


__all__ = ["DEFAULT_GAME", "GAMES", "get_game", "DomainGame"]
