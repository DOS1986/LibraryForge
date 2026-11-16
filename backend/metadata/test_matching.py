from django.test import SimpleTestCase

from metadata.providers import ExternalId, MetadataCandidate
from metadata.services.matching import MatchTarget, match_hint, normalize_title


def _candidate(**overrides):
    values = {
        "provider": "tmdb",
        "target_type": "movie",
        "source_id": "603",
        "title": "The Matrix",
        "release_date": "1999-03-30",
    }
    values.update(overrides)
    return MetadataCandidate(**values)


def _codes(hint):
    return [reason["code"] for reason in hint["reasons"]]


class NormalizeTitleTests(SimpleTestCase):
    def test_comparison_form(self):
        self.assertEqual(normalize_title("The Matrix"), "matrix")
        self.assertEqual(normalize_title("Amélie"), "amelie")
        self.assertEqual(normalize_title("Fast & Furious"), "fast and furious")
        self.assertEqual(normalize_title("  WALL·E!! "), "wall e")
        self.assertEqual(normalize_title(""), "")


class MatchHintTests(SimpleTestCase):
    def test_exact_title_and_year_is_likely_not_strong(self):
        hint = match_hint(MatchTarget(title="The Matrix", year=1999), _candidate())
        self.assertEqual(hint["tier"], "likely")
        self.assertEqual(_codes(hint), ["title_exact", "year_same"])

    def test_external_id_agreement_is_strong(self):
        target = MatchTarget(title="Matrix", year=None, external_ids={"imdb": "tt0133093"})
        hint = match_hint(target, _candidate(external_ids=(ExternalId("imdb", "tt0133093"),)))
        self.assertEqual(hint["tier"], "strong")
        self.assertIn("external_id_match", _codes(hint))

    def test_conflicting_external_id_outranks_everything(self):
        target = MatchTarget(title="The Matrix", year=1999, external_ids={"tmdb": "999"})
        hint = match_hint(target, _candidate(external_ids=(ExternalId("tmdb", "603"),)))
        self.assertEqual(hint["tier"], "conflict")
        self.assertIn("external_id_conflict", _codes(hint))

    def test_remake_is_flagged(self):
        hint = match_hint(MatchTarget(title="Dune", year=2021), _candidate(title="Dune", release_date="1984-12-14"))
        self.assertIn("possible_remake", _codes(hint))
        self.assertIn("Year differs by 37", " ".join(reason["label"] for reason in hint["reasons"]))
        self.assertEqual(hint["tier"], "weak")

    def test_original_title_match_and_punctuation(self):
        hint = match_hint(
            MatchTarget(title="La casa de papel", year=2017),
            _candidate(target_type="series", title="Money Heist", original_title="La casa de papel", release_date="2017"),
        )
        self.assertIn("original_title_match", _codes(hint))
        hint = match_hint(MatchTarget(title="wall-e"), _candidate(title="WALL·E", release_date=None))
        self.assertEqual(_codes(hint), ["title_normalized", "year_unknown"])
        self.assertEqual(hint["tier"], "possible")

    def test_unrelated_title_is_weak(self):
        hint = match_hint(MatchTarget(title="Inception", year=2010), _candidate())
        self.assertEqual(hint["tier"], "weak")
        self.assertIn("title_differs", _codes(hint))

    def test_reasons_have_tones(self):
        hint = match_hint(MatchTarget(title="The Matrix", year=2000), _candidate())
        self.assertEqual({reason["tone"] for reason in hint["reasons"]}, {"positive", "neutral"})
