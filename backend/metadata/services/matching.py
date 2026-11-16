"""Explainable match hints between a catalog target and provider candidates.

A hint helps a person choose; it is never permission to change catalog data.
The tier is an ordered label, not a calibrated probability, and no tier ever
triggers an automatic apply.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from metadata.providers.types import MetadataCandidate

TIER_STRONG = "strong"
TIER_LIKELY = "likely"
TIER_POSSIBLE = "possible"
TIER_WEAK = "weak"
TIER_CONFLICT = "conflict"

TONE_POSITIVE = "positive"
TONE_NEUTRAL = "neutral"
TONE_WARNING = "warning"

SIMILAR_TITLE_RATIO = 0.85
_LEADING_ARTICLES = ("the ", "a ", "an ")
_NAMESPACE_LABELS = {"imdb": "IMDb", "tmdb": "TMDB", "tvdb": "TVDB", "wikidata": "Wikidata"}


@dataclass(frozen=True)
class MatchTarget:
    """What LibraryForge currently knows about the item being matched."""

    title: str
    original_title: str = ""
    year: int | None = None
    external_ids: dict[str, str] = field(default_factory=dict)


def normalize_title(value: str) -> str:
    """Comparison form only; the displayed spelling is never changed."""

    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = " ".join(text.split())
    for article in _LEADING_ARTICLES:
        if text.startswith(article):
            text = text[len(article) :]
            break
    return text


def _title_ratio(left: str, right: str) -> float:
    a, b = normalize_title(left), normalize_title(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _reason(code: str, label: str, tone: str) -> dict[str, str]:
    return {"code": code, "label": label, "tone": tone}


def match_hint(target: MatchTarget, candidate: MetadataCandidate) -> dict[str, Any]:
    reasons: list[dict[str, str]] = []
    points = 0

    # External IDs are the strongest evidence, and a conflict outranks
    # everything else because it suggests two different works.
    candidate_ids = {item.namespace: item.value for item in candidate.external_ids}
    id_matches: list[str] = []
    id_conflicts: list[str] = []
    for namespace, value in sorted(target.external_ids.items()):
        other = candidate_ids.get(str(namespace).casefold())
        if other is None or not str(value).strip():
            continue
        label = _NAMESPACE_LABELS.get(str(namespace).casefold(), str(namespace))
        if str(value).strip().casefold() == other.casefold():
            id_matches.append(label)
        else:
            id_conflicts.append(label)
    for label in id_matches:
        reasons.append(_reason("external_id_match", f"{label} ID matches", TONE_POSITIVE))
    for label in id_conflicts:
        reasons.append(_reason("external_id_conflict", f"{label} ID differs from this item's", TONE_WARNING))

    titles = [candidate.title] + ([candidate.original_title] if candidate.original_title else [])
    targets = [target.title] + ([target.original_title] if target.original_title else [])
    best = max((_title_ratio(left, right) for left in targets for right in titles), default=0.0)
    if best == 1.0:
        exact_display = candidate.title.strip() == target.title.strip()
        if exact_display:
            reasons.append(_reason("title_exact", "Title matches", TONE_POSITIVE))
        elif candidate.original_title and _title_ratio(target.title, candidate.original_title) == 1.0:
            reasons.append(_reason("original_title_match", "Matches the original title", TONE_POSITIVE))
        else:
            reasons.append(_reason("title_normalized", "Title matches apart from punctuation or case", TONE_POSITIVE))
        points += 2
    elif best >= SIMILAR_TITLE_RATIO:
        reasons.append(_reason("title_similar", "Title is similar", TONE_NEUTRAL))
        points += 1
    else:
        reasons.append(_reason("title_differs", "Title differs", TONE_WARNING))

    if target.year is None or candidate.year is None:
        reasons.append(_reason("year_unknown", "Year can't be compared", TONE_NEUTRAL))
    else:
        difference = abs(target.year - candidate.year)
        if difference == 0:
            reasons.append(_reason("year_same", f"Same year ({candidate.year})", TONE_POSITIVE))
            points += 2
        elif difference == 1:
            reasons.append(_reason("year_close", f"Year differs by 1 ({candidate.year})", TONE_NEUTRAL))
            points += 1
        else:
            reasons.append(
                _reason("year_differs", f"Year differs by {difference} ({candidate.year})", TONE_WARNING)
            )
            points -= 1
            if best == 1.0:
                reasons.append(
                    _reason("possible_remake", "Same title but a different year: could be a remake", TONE_WARNING)
                )

    if id_conflicts:
        tier = TIER_CONFLICT
    elif id_matches:
        tier = TIER_STRONG
    elif points >= 4:
        tier = TIER_LIKELY
    elif points >= 2:
        tier = TIER_POSSIBLE
    else:
        tier = TIER_WEAK

    return {"tier": tier, "reasons": reasons}
