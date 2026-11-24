"""
backend.domain.letter_facts
===========================

Deterministic fact-check for the cover letter: which numbers in the
draft are backed by the candidate's own documents, and which ones the
model made up.

Why this module exists
----------------------
The prompt already forbids inventing figures ("ZERO HALLUCINATION",
"FACT CHECK BEFORE ANSWERING"), and the prompt is not enough. A letter
is prose, and prose is where a model slides: it writes "atendí a más de
120 clientes por día" because that is the shape of a sentence about
service, and the figure is not in the CV at all.

The CV pipeline does not have this problem: it is a structured
document, and the renderer can compare the YAML against the source. A
letter has no such structure to diff against — so the check has to be
made on the numbers themselves.

The rule implemented here is simple and auditable:

    A number that appears in the letter must appear in the resume (or in
    the job description, which is real input the candidate answered).

Numbers are normalised before comparison, because the same figure is
written in different ways: ``2.000`` / ``2,000`` / ``2000`` are the same
number, and ``4,5`` / ``4.5`` are the same number. Both sides of the
comparison go through the same normalisation, so the check never
compares apples to oranges.

What is deliberately NOT flagged
--------------------------------
* Small integers (1 to 12). "las tres responsabilidades", "en 2 años":
  counts and ordinals are part of the sentence structure, not invented
  metrics. A decimal like ``4,5`` is always checked.
* URLs, e-mail addresses and phone numbers. Those are contact data,
  and the letterhead is built by the backend anyway.
* Numbers that only exist in the job description. The vacancy is a real
  document: quoting "los 3 años de experiencia que pide la vacante" is
  not a claim about the candidate, so it is not a hallucination.

Everything else that the resume does not back is a hallucination, and
the caller drops the sentence that carries it.
"""

from __future__ import annotations

import re
from typing import Iterable


# --- Number extraction ------------------------------------------------------

#: A number as written: digits, optionally grouped by "." or ",", optionally
#: with the "K"/"M" shorthand a resume uses ("50K+ lines of code").
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*\s*[kKmM]?\+?")

#: Things that look like numbers but are contact data.
_URL_RE = re.compile(
    r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|net|org|co|io|dev|es|mx|ar|cl)\b\S*",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

#: A candidate phone number. The shape check below decides whether a
#: match is really a phone: "2014 - 2018" has the same structure as a
#: phone, so two four-digit year groups are treated as a date range.
_PHONE_CANDIDATE_RE = re.compile(r"[+\d][\d\s().-]{5,}\d")
_YEAR_GROUP_RE = re.compile(r"(?:19|20)\d{2}")

#: Small integers are structure (counts, ordinals), not invented metrics.
_TRIVIAL_MAX = 12


def normalize_number(raw: str) -> str:
    """Normalise a number as written so two spellings compare equal.

    ``"2.000"``  → ``"2000"``   (thousands, Spanish or English)
    ``"4,5"``    → ``"4.5"``    (decimal, Spanish)
    ``"4.5"``    → ``"4.5"``    (decimal, English)
    ``"2,000"``  → ``"2000"``   (thousands, English)
    ``"50K+"``   → ``"50000"``  (the "K" shorthand a resume uses)
    ``"2K+"``    → ``"2000"``
    ``"1.5K"``   → ``"1500"``

    The last group matters in practice: a resume writes "50K+ lines of
    code" and a letter translates it to "50.000 líneas". Both sides go
    through the same normalisation, so the translation is recognised as
    the same figure instead of being reported as an invention.
    """
    raw = raw.strip().rstrip(".,;:")
    if not raw:
        return ""

    multiplier = 1
    shorthand = re.search(r"([kKmM])\s*\+?$", raw)
    if shorthand:
        multiplier = 1_000 if shorthand.group(1).lower() == "k" else 1_000_000
        raw = raw[: shorthand.start()].strip()
        if not raw:
            return ""

    if "." in raw and "," in raw:
        # Both separators present: the rightmost one is the decimal mark.
        if raw.rfind(".") > raw.rfind(","):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(".", "").replace(",", ".")
    elif "." in raw:
        head, _, tail = raw.partition(".")
        # Exactly three digits after the dot means a thousands group
        # ("50.000"), anything else means a decimal ("4.5").
        raw = head + tail if (len(tail) == 3 and head) else raw
    elif "," in raw:
        head, _, tail = raw.partition(",")
        raw = head + tail if (len(tail) == 3 and head) else head + "." + tail

    if multiplier != 1:
        try:
            value = float(raw)
        except ValueError:
            return ""
        value *= multiplier
        return str(int(value)) if value.is_integer() else str(value)

    return raw


def _is_trivial(value: str) -> bool:
    """True for small integers, which are counts and not invented metrics."""
    if not value.isdigit():
        return False  # decimals and fractions are always checked
    try:
        return 0 < int(value) <= _TRIVIAL_MAX
    except ValueError:
        return False


def _looks_like_phone(candidate: str) -> bool:
    """True when a candidate match is a phone number, not a date range.

    "123-456-7890" is a phone. "2014 - 2018" has the same shape, so two
    four-digit groups that both look like years are kept as dates.
    """
    digits = re.sub(r"\D", "", candidate)
    if not (7 <= len(digits) <= 15):
        return False
    groups = [part for part in re.split(r"[\s().-]+", candidate) if part]
    if len(groups) == 2 and all(_YEAR_GROUP_RE.fullmatch(g) for g in groups):
        return False
    return True


def _strip_contact_noise(text: str) -> str:
    """Remove URLs, e-mails and phone numbers before scanning for numbers."""
    text = _URL_RE.sub(" ", text)
    text = _EMAIL_RE.sub(" ", text)
    text = _PHONE_CANDIDATE_RE.sub(
        lambda m: " " if _looks_like_phone(m.group(0)) else m.group(0), text
    )
    return text


def numbers_in(text: str) -> list[str]:
    """Every non-trivial number in ``text``, normalised, in order of appearance."""
    if not text:
        return []
    found: list[str] = []
    for raw in _NUMBER_RE.findall(_strip_contact_noise(text)):
        value = normalize_number(raw)
        if not value or _is_trivial(value):
            continue
        found.append(value)
    return found


def _allowed_numbers(*sources: str) -> set[str]:
    """The set of numbers the candidate's real documents contain."""
    allowed: set[str] = set()
    for source in sources:
        if not source:
            continue
        for value in numbers_in(source):
            allowed.add(value)
    return allowed


def find_unsupported_numbers(
    letter_text: str,
    resume_text: str = "",
    jd_text: str = "",
) -> list[str]:
    """Numbers in the letter that no source document backs.

    Args:
        letter_text: the draft letter (prose only).
        resume_text: the candidate's real resume text.
        jd_text: the job description — a real input, so its numbers are
            allowed (the letter may quote a requirement).

    Returns:
        The normalised offending numbers, de-duplicated, in the order they
        appear in the letter. Empty when the letter is clean.
    """
    allowed = _allowed_numbers(resume_text, jd_text)
    unsupported: list[str] = []
    for value in numbers_in(letter_text):
        if value in allowed:
            continue
        if value not in unsupported:
            unsupported.append(value)
    return unsupported


# --- Sentence removal -------------------------------------------------------

#: Split a paragraph into sentences, keeping the punctuation.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def split_sentences(text: str) -> list[str]:
    """Split a paragraph into sentences. Empty input yields an empty list."""
    if not text:
        return []
    return [part for part in _SENTENCE_SPLIT_RE.split(text.strip()) if part.strip()]


def remove_sentences_with_numbers(
    text: str,
    unsupported: Iterable[str],
    *,
    resume_text: str = "",
    jd_text: str = "",
) -> str:
    """Drop every sentence that carries one of the unsupported numbers.

    A sentence is only dropped when the number is genuinely unbacked:
    the allowed set is recomputed from the sources, so a sentence that
    mentions a supported number elsewhere survives.
    """
    bad = {str(value) for value in unsupported}
    if not bad or not text:
        return text

    allowed = _allowed_numbers(resume_text, jd_text)
    kept: list[str] = []
    for sentence in split_sentences(text):
        offending = [
            value for value in numbers_in(sentence) if value in bad and value not in allowed
        ]
        if offending:
            continue
        kept.append(sentence)
    return " ".join(kept)


__all__ = [
    "find_unsupported_numbers",
    "normalize_number",
    "numbers_in",
    "remove_sentences_with_numbers",
    "split_sentences",
]
