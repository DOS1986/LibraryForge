"""Golden naming and NFO fixtures for every output profile.

The fixtures in ``outputs/golden/`` are the reviewed output: one file list
per profile and layout, and the NFOs (the same for every profile). To
regenerate them after a deliberate change, run the tests with
``LIBRARYFORGE_UPDATE_GOLDEN=1`` and review the diff.
"""

import datetime
import os
from pathlib import Path

from catalog.models import ArtworkFile, Episode, Season, Series
from media.models import MediaItem
from outputs.models import OutputProfile, ProjectionPlan
from outputs.services import movies_tv
from outputs.test_movies_tv import _Base

GOLDEN = Path(__file__).parent / "golden"
UPDATE = os.environ.get("LIBRARYFORGE_UPDATE_GOLDEN") == "1"
Art = ArtworkFile.ArtworkType


class GoldenTests(_Base):
    maxDiff = None

    def setUp(self):
        super().setUp()
        self.movies = self.library("Movies", "movies")
        movie = MediaItem.objects.create(
            library=self.movies, title="The Matrix", original_title="The Matrix", media_type=MediaItem.MediaType.MOVIE,
            content_rating="R", description="Neo wakes up.", tagline="Free your mind.", genres=["Action", "Sci-Fi"],
            studios=["Warner Bros."], release_date=datetime.date(1999, 3, 31), external_ids={"imdb": "tt0133093", "tmdb": "603"},
        )
        self.file(self.movies, movie, "matrix/the.matrix.1999.mkv")
        target = ArtworkFile.TargetType.MEDIA_ITEM
        self.art(self.movies, target, movie.id, "matrix/poster.jpg", Art.PRIMARY)
        self.art(self.movies, target, movie.id, "matrix/fanart.jpg", Art.BACKDROP)
        self.art(self.movies, target, movie.id, "matrix/logo.png", Art.LOGO)
        self.art(self.movies, target, movie.id, "matrix/banner.jpg", Art.BANNER)
        self.art(self.movies, target, movie.id, "matrix/landscape.jpg", Art.THUMB)

        self.tv = self.library("TV", "tv")
        series = Series.objects.create(
            library=self.tv, title="Bluey", semantic_key="bluey", start_year=2018, content_rating="TV-Y",
            description="A Blue Heeler puppy.", external_ids={"tvdb": "353546", "imdb": "tt7678620"},
        )
        specials = Season.objects.create(series=series, season_number=0, title="Specials")
        season = Season.objects.create(series=series, season_number=1, title="Season 1")
        first = self.episode(series, season, 1, "Magic Xylophone")
        self.episode(series, season, 2, "Hospital")
        self.episode(series, specials, 1, "The Sign Extended")
        self.art(self.tv, ArtworkFile.TargetType.SERIES, series.id, "Bluey/poster.jpg", Art.PRIMARY)
        self.art(self.tv, ArtworkFile.TargetType.SERIES, series.id, "Bluey/fanart.jpg", Art.BACKDROP)
        self.art(self.tv, ArtworkFile.TargetType.SERIES, series.id, "Bluey/clearlogo.png", Art.LOGO)
        self.art(self.tv, ArtworkFile.TargetType.SEASON, season.id, "Bluey/Season 1/folder.jpg", Art.PRIMARY)
        self.art(self.tv, ArtworkFile.TargetType.SEASON, specials.id, "Bluey/Specials/folder.jpg", Art.PRIMARY)
        self.art(self.tv, ArtworkFile.TargetType.EPISODE, first.id, "Bluey/Season 1/e01-thumb.jpg", Art.THUMB)

    def episode(self, series, season, number, title):
        item = MediaItem.objects.create(
            library=self.tv, title=title, media_type=MediaItem.MediaType.TV_EPISODE, description=f"{title}.",
        )
        episode = Episode.objects.create(
            media_item=item, season=season, episode_number=number, air_date=datetime.date(2018, 10, number),
        )
        self.file(self.tv, item, f"Bluey/Season {season.season_number}/e{number:02d}.mkv")
        return episode

    def profile(self, target):
        return OutputProfile.objects.create(owner=self.user, name=f"{target} profile", target=target)

    def golden(self, name: str, actual: str):
        path = GOLDEN / name
        if UPDATE:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(actual, encoding="utf-8", newline="\n")
        self.assertTrue(path.exists(), f"Missing golden fixture {name}; run with LIBRARYFORGE_UPDATE_GOLDEN=1.")
        self.assertEqual(actual, path.read_text(encoding="utf-8"), f"{name} differs from its golden fixture")

    def check(self, target):
        profile = self.profile(target)
        nfos = {}
        for library, layout in ((self.movies, "movies"), (self.tv, "tv")):
            projection = self.create(library, name=f"{target}-{layout}", output_profile=str(profile.id))
            data = self.plan(projection)
            self.assertEqual(data["status"], "ready", data["findings"])
            self.assertEqual(data["overview"]["profile"]["target"], target)
            self.golden(f"{target}/{layout}.txt", "".join(f"{path}\n" for path in sorted(data["paths"])))
            for row in ProjectionPlan.objects.get(id=data["id"]).actions.exclude(content=""):
                nfos[row.relative_path.rsplit("/", 1)[-1]] = row.content
        return nfos

    def test_profiles_share_one_nfo_dialect(self):
        outputs = {target: self.check(target) for target in OutputProfile.Target.values}
        reference = outputs["jellyfin"]
        for target, nfos in outputs.items():
            self.assertEqual(nfos, reference, f"{target} NFOs differ from Jellyfin's")
        for name, golden_name in (
            ("The Matrix (1999).nfo", "nfo/movie.nfo"),
            ("tvshow.nfo", "nfo/tvshow.nfo"),
            ("Bluey S01E01 - Magic Xylophone.nfo", "nfo/episode.nfo"),
            ("Bluey S00E01 - The Sign Extended.nfo", "nfo/special.nfo"),
        ):
            self.golden(golden_name, reference[name])

    def test_kodi_names_follow_its_scanner(self):
        self.check("kodi")
        movies = (GOLDEN / "kodi/movies.txt").read_text("utf-8").split()
        self.assertTrue(any(line.endswith("(1999)-clearlogo.png") for line in movies))
        tv = (GOLDEN / "kodi/tv.txt").read_text("utf-8").splitlines()
        self.assertIn("Bluey (2018)/season01-poster.jpg", tv)
        self.assertIn("Bluey (2018)/season-specials-poster.jpg", tv)
        self.assertFalse(any(line.startswith("Bluey (2018)/Season 01/poster") for line in tv))

    def test_generic_projects_poster_and_fanart_only(self):
        self.check("generic")
        lines = (GOLDEN / "generic/movies.txt").read_text("utf-8").splitlines()
        art = sorted(line.rsplit("/", 1)[-1] for line in lines if line.endswith((".jpg", ".png")))
        self.assertEqual(art, ["fanart.jpg", "poster.jpg"])

    def test_changing_profile_replaces_open_plans_and_renames_art(self):
        jellyfin = self.profile("jellyfin")
        kodi = self.profile("kodi")
        projection = self.create(self.movies, output_profile=str(jellyfin.id))
        self.apply(projection)
        open_plan = self.plan(projection)

        response = self.client.patch(f"/api/projections/{projection.id}/", {"output_profile": str(kodi.id)}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ProjectionPlan.objects.get(id=open_plan["id"]).status, "superseded")
        data = self.plan(projection)
        self.assertEqual(data["paths"]["The Matrix (1999)/poster.jpg"], "delete")
        self.assertEqual(data["paths"]["The Matrix (1999)/The Matrix (1999)-poster.jpg"], "create")
        self.assertNotIn("The Matrix (1999)/The Matrix (1999).nfo", data["paths"])  # NFO unchanged

    def test_target_picks_or_creates_a_profile(self):
        projection = self.create(self.movies, name="k", target="kodi")
        self.assertEqual(projection.output_profile.target, "kodi")
        self.assertEqual(projection.name, "Kodi movies")
        again = self.create(self.tv, name="k2", target="kodi")
        self.assertEqual(again.output_profile_id, projection.output_profile_id)
        response = self.client.post(
            f"/api/libraries/{self.movies.id}/projections/",
            {"destination_path": str(self.tmp / "out" / "z"), "target": "plex"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_target_falls_back_to_generic_names(self):
        self.assertEqual(movies_tv.profiles.for_target("unknown").target, "generic")
