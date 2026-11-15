"""Estimate a US content rating from other countries' ratings.

When a provider has no US certification for a title, the ratings it does
have from other countries still say a lot. Each known rating is converted to
the minimum age it implies, the ages are combined, and the result is mapped
onto the US movie (MPA) or TV Parental Guidelines scale.

This is an estimate for a person to review, never an automatic value:

* Ages come from each system's published age bands. Systems differ in what
  they weigh (violence, language, themes), so the mapping is approximate.
* The upper middle age is used (the median, rounding toward the stricter
  side with an even count), so one unusually strict or lenient country
  doesn't decide the result, and ties lean stricter.
* TV-Y and TV-Y7 describe programmes *made for* children, which an age
  alone can't tell, so they are never estimated; TV-G is the lowest TV
  estimate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Minimum viewer age implied by each rating, per ISO 3166-1 country. Values
# cover common movie and TV certifications as providers report them.
_AGES: dict[str, dict[str, int]] = {
    "GB": {"U": 0, "UC": 0, "PG": 8, "12": 12, "12A": 12, "15": 15, "18": 18, "R18": 18},
    "IE": {"G": 0, "PG": 8, "12": 12, "12A": 12, "15": 15, "15A": 15, "16": 16, "18": 18},
    "CA": {
        "G": 0, "PG": 8, "14A": 14, "18A": 18, "R": 18, "A": 18,
        "C": 0, "C8": 8, "14+": 14, "18+": 18, "E": 0,
    },
    "AU": {
        "G": 0, "PG": 8, "M": 15, "MA15+": 15, "MA 15+": 15, "R18+": 18, "R 18+": 18, "X18+": 18,
        "P": 0, "C": 0, "AV15+": 15,
    },
    "NZ": {
        "G": 0, "PG": 8, "M": 13, "R13": 13, "RP13": 13, "R15": 15, "R16": 16, "RP16": 16,
        "R18": 18, "RP18": 18, "R": 18,
    },
    "DE": {"0": 0, "6": 6, "12": 12, "16": 16, "18": 18},
    "AT": {"0": 0, "6": 6, "10": 10, "12": 12, "14": 14, "16": 16, "18": 18},
    "CH": {"0": 0, "6": 6, "8": 8, "10": 10, "12": 12, "14": 14, "16": 16, "18": 18},
    "FR": {"U": 0, "TP": 0, "10": 10, "12": 12, "16": 16, "18": 18},
    "NL": {"AL": 0, "6": 6, "9": 9, "12": 12, "14": 14, "16": 16, "18": 18},
    "BE": {"AL": 0, "KT": 0, "6": 6, "9": 9, "12": 12, "14": 14, "16": 16, "18": 18},
    "ES": {"A": 0, "APTA": 0, "TP": 0, "7": 7, "12": 12, "13": 13, "16": 16, "18": 18, "X": 18},
    "PT": {"T": 0, "M/3": 3, "M/6": 6, "M/12": 12, "M/14": 14, "M/16": 16, "M/18": 18},
    "IT": {"T": 0, "6+": 6, "14": 14, "14+": 14, "VM14": 14, "18": 18, "18+": 18, "VM18": 18},
    "BR": {"L": 0, "10": 10, "12": 12, "14": 14, "16": 16, "18": 18},
    "MX": {"AA": 0, "A": 0, "B": 12, "B-15": 15, "C": 18, "D": 18},
    "SE": {"BTL": 0, "7": 7, "11": 11, "15": 15},
    "NO": {"A": 0, "6": 6, "9": 9, "12": 12, "15": 15, "18": 18},
    "DK": {"A": 0, "7": 7, "11": 11, "15": 15},
    "FI": {"S": 0, "K-7": 7, "K-12": 12, "K-16": 16, "K-18": 18, "7": 7, "12": 12, "16": 16, "18": 18},
    "JP": {"G": 0, "PG12": 12, "R15+": 15, "R18+": 18},
    "KR": {"ALL": 0, "7": 7, "12": 12, "15": 15, "18": 18, "19": 19},
    "IN": {"U": 0, "UA": 12, "U/A": 12, "U/A 7+": 7, "U/A 13+": 13, "U/A 16+": 16, "A": 18},
}

# Pure age-style values ("12", "16+", "FSK 16") read the same in most systems.
_NUMERIC = re.compile(r"^(?:FSK\s*|K-?|M/)?(\d{1,2})\+?$", re.IGNORECASE)


@dataclass(frozen=True)
class RatingBasis:
    territory: str
    rating: str
    age: int


@dataclass(frozen=True)
class RatingEstimate:
    value: str
    basis: tuple[RatingBasis, ...]

    @property
    def age(self) -> int:
        ages = sorted(item.age for item in self.basis)
        return ages[len(ages) // 2]

    def describe(self) -> str:
        countries = ", ".join(f"{item.territory} {item.rating}" for item in self.basis)
        return f"Estimated from other countries' ratings ({countries})."

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "age": self.age,
            "basis": [{"territory": item.territory, "rating": item.rating, "age": item.age} for item in self.basis],
        }


def rating_age(territory: str, rating: str) -> int | None:
    """Minimum age implied by one country's rating, or None if unknown."""

    value = " ".join((rating or "").split()).upper()
    if not value:
        return None
    table = _AGES.get((territory or "").upper())
    if table and value in table:
        return table[value]
    match = _NUMERIC.fullmatch(value)
    if match:
        age = int(match.group(1))
        return age if age <= 21 else None
    return None


def us_movie_rating(age: int) -> str:
    if age <= 0:
        return "G"
    if age <= 9:
        return "PG"
    if age <= 14:
        return "PG-13"
    return "R"


def us_tv_rating(age: int) -> str:
    if age <= 0:
        return "TV-G"
    if age <= 9:
        return "TV-PG"
    if age <= 14:
        return "TV-14"
    return "TV-MA"


def estimate_us_rating(ratings: list[tuple[str, str]], *, tv: bool) -> RatingEstimate | None:
    """Estimate a US rating from (territory, rating) pairs; US entries are ignored."""

    basis = []
    for territory, rating in ratings:
        if (territory or "").upper() == "US":
            continue
        age = rating_age(territory, rating)
        if age is not None:
            basis.append(RatingBasis(territory.upper(), rating, age))
    if not basis:
        return None
    ages = sorted(item.age for item in basis)
    age = ages[len(ages) // 2]
    value = us_tv_rating(age) if tv else us_movie_rating(age)
    return RatingEstimate(value=value, basis=tuple(sorted(basis, key=lambda item: item.territory)))
