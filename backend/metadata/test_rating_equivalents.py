from django.test import SimpleTestCase

from metadata.services.rating_equivalents import estimate_us_rating, rating_age


class RatingAgeTests(SimpleTestCase):
    def test_known_systems_and_numeric_forms(self):
        cases = [
            ("GB", "12A", 12),
            ("GB", "u", 0),
            ("AU", "MA15+", 15),
            ("NZ", "R16", 16),
            ("CA", "14A", 14),
            ("FR", "TP", 0),
            ("FI", "K-12", 12),
            ("JP", "PG12", 12),
            ("XX", "16", 16),
            ("XX", "FSK 12", 12),
            ("XX", "12+", 12),
            ("XX", "Banned", None),
            ("GB", "", None),
            ("XX", "99", None),
        ]
        for territory, rating, age in cases:
            with self.subTest(territory=territory, rating=rating):
                self.assertEqual(rating_age(territory, rating), age)


class EstimateTests(SimpleTestCase):
    def test_movies_use_the_upper_middle_age(self):
        estimate = estimate_us_rating([("GB", "15"), ("DE", "16"), ("FR", "12")], tv=False)
        self.assertEqual((estimate.value, estimate.age), ("R", 15))
        estimate = estimate_us_rating([("GB", "12A"), ("DE", "6")], tv=False)
        # Two values: the stricter one decides.
        self.assertEqual((estimate.value, estimate.age), ("PG-13", 12))
        self.assertEqual(estimate_us_rating([("GB", "U"), ("DE", "0")], tv=False).value, "G")
        self.assertEqual(estimate_us_rating([("GB", "PG")], tv=False).value, "PG")

    def test_tv_scale_never_guesses_childrens_ratings(self):
        self.assertEqual(estimate_us_rating([("GB", "U")], tv=True).value, "TV-G")
        self.assertEqual(estimate_us_rating([("DE", "6")], tv=True).value, "TV-PG")
        self.assertEqual(estimate_us_rating([("CA", "14+")], tv=True).value, "TV-14")
        self.assertEqual(estimate_us_rating([("AU", "MA15+")], tv=True).value, "TV-MA")

    def test_us_and_unknown_entries_are_ignored(self):
        self.assertIsNone(estimate_us_rating([("US", "R"), ("ZZ", "Banned")], tv=False))
        estimate = estimate_us_rating([("US", "G"), ("GB", "18")], tv=False)
        self.assertEqual([item.territory for item in estimate.basis], ["GB"])
        self.assertIn("GB 18", estimate.describe())
