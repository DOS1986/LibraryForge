"""Apply tests: the only metadata-provider path that writes catalog data."""

import datetime
import uuid
from unittest.mock import patch

from django.core.cache import cache
from rest_framework.test import APIClient

from catalog.models import CanonicalFieldState, MetadataChangeSet
from catalog.services.canonical import (
    is_field_locked,
    serialize_history,
    set_field_provenance,
)
from integrations.tests.test_tmdb import MOVIE_DETAIL, SERIES_DETAIL, TOKEN
from metadata.test_provider_match import _MatchApiTestCase


class _ApplyTestCase(_MatchApiTestCase):
    def setUp(self):
        super().setUp()
        self.detail = MOVIE_DETAIL
        self.request.side_effect = lambda url, **kwargs: (SERIES_DETAIL if "/tv/" in url else self.detail)

    def preview(self, kind="movie", target=None, **params):
        target = target or (self.movie if kind == "movie" else self.series)
        source_id = "603" if kind == "movie" else "1396"
        response = self.client.get(self.url(kind, target.id, "preview"), {"source_id": source_id, **params})
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        return response.data

    def body(self, preview, fields, **overrides):
        return {
            "connection": preview["connection"]["connection_id"],
            "source_id": preview["source_id"],
            "territory": preview["territory"],
            "fields": fields,
            "target_revision": preview["target_revision"],
            "provider_snapshot": preview["provider_snapshot"],
            "operation_id": str(uuid.uuid4()),
            **overrides,
        }

    def apply(self, body, kind="movie", target=None):
        target = target or (self.movie if kind == "movie" else self.series)
        return self.client.post(self.url(kind, target.id, "apply"), body, format="json")

    def states(self, target=None, target_type=CanonicalFieldState.TargetType.MEDIA_ITEM):
        target = target or self.movie
        return {
            state.field_name: state
            for state in CanonicalFieldState.objects.filter(target_type=target_type, target_id=target.id)
        }


class ApplyTests(_ApplyTestCase):
    def test_applies_only_chosen_fields_with_provenance(self):
        preview = self.preview()
        response = self.apply(self.body(preview, ["tagline", "studios", "release_date", "external_ids.tmdb"]))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["applied"])
        self.assertFalse(response.data["replayed"])

        self.movie.refresh_from_db()
        self.assertEqual(self.movie.tagline, "Welcome to the Real World.")
        self.assertEqual(self.movie.studios, ["Village Roadshow Pictures", "Warner Bros. Pictures"])
        self.assertEqual(self.movie.release_date, datetime.date(1999, 3, 30))
        self.assertEqual(self.movie.external_ids, {"imdb": "tt0133093", "tmdb": "603"})
        # Fields offered but not chosen are untouched.
        self.assertEqual(self.movie.description, "")
        self.assertEqual(self.movie.genres, ["Action"])
        self.assertEqual(self.movie.title, "The Matrix")

        states = self.states()
        self.assertEqual(set(states), {"tagline", "studios", "release_date", "external_ids"})
        for state in states.values():
            self.assertEqual(state.source, CanonicalFieldState.Source.PROVIDER)
            self.assertEqual(state.source_ref, "tmdb:movie:603")
            self.assertTrue(state.locked)
            self.assertEqual(state.updated_by, self.user)

        change_set = MetadataChangeSet.objects.get()
        self.assertEqual(change_set.source, MetadataChangeSet.Source.PROVIDER)
        self.assertEqual(change_set.changed_by, self.user)
        self.assertEqual(set(change_set.changes), {"tagline", "studios", "release_date", "external_ids"})
        self.assertEqual(change_set.changes["tagline"], {"old": "", "new": "Welcome to the Real World."})
        self.assertEqual(change_set.details["source_id"], "603")
        self.assertEqual(change_set.details["provider"], "tmdb")
        self.assertIn("retrieved_at", change_set.details)
        self.assertNotIn(TOKEN, str(change_set.details) + str(change_set.changes))

        history = response.data["detail"]["history"]
        self.assertEqual(history[0]["source"], "provider")
        self.assertEqual(history[0]["source_ref"], "tmdb:movie:603")

    def test_values_come_from_server_not_the_request(self):
        preview = self.preview()
        body = self.body(preview, ["tagline"], tagline="Injected", values={"tagline": "Injected"}, title="Hacked")
        self.assertEqual(self.apply(body).status_code, 200)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.tagline, "Welcome to the Real World.")
        self.assertEqual(self.movie.title, "The Matrix")

    def test_release_date_brings_the_year(self):
        self.movie.canonical_metadata = {"semantic": {"kind": "movie", "year": 2003}}
        self.movie.save()
        preview = self.preview()
        self.assertEqual(self.apply(self.body(preview, ["release_date"])).status_code, 200)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.release_date, datetime.date(1999, 3, 30))
        self.assertEqual(self.movie.canonical_metadata["semantic"]["year"], 1999)
        self.assertEqual(MetadataChangeSet.objects.get().changes["year"], {"old": 2003, "new": 1999})

    def test_year_alone_cannot_contradict_release_date(self):
        self.movie.release_date = datetime.date(1999, 3, 31)
        self.movie.save()
        self.detail = {**MOVIE_DETAIL, "release_date": "2001-05-01"}
        preview = self.preview()
        response = self.apply(self.body(preview, ["year"]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("disagree", response.data["detail"])
        self.assertEqual(MetadataChangeSet.objects.count(), 0)

    def test_list_fields_only_add(self):
        preview = self.preview()
        self.assertEqual(self.apply(self.body(preview, ["genres"])).status_code, 200)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.genres, ["Action", "Science Fiction"])

    def test_series_apply(self):
        preview = self.preview(kind="series")
        response = self.apply(self.body(preview, ["end_year", "external_ids.tvdb", "content_rating"]), kind="series")
        self.assertEqual(response.status_code, 200, response.data)
        self.series.refresh_from_db()
        self.assertEqual((self.series.start_year, self.series.end_year), (2008, 2013))
        self.assertEqual(self.series.external_ids, {"tvdb": "81189"})
        self.assertEqual(self.series.content_rating, "TV-MA")
        states = self.states(self.series, CanonicalFieldState.TargetType.SERIES)
        self.assertEqual(states["end_year"].source_ref, "tmdb:series:1396")


class RejectionTests(_ApplyTestCase):
    def assertNothingWritten(self, before):
        self.assertEqual(self.catalog_snapshot(), before)

    def test_unknown_and_unselectable_fields(self):
        preview = self.preview()
        before = self.catalog_snapshot()
        for fields, text in (
            (["bogus"], "Unknown fields"),
            (["title"], "can't be applied"),
            (["sort_title"], "can't be applied"),
            (["external_ids.imdb"], "can't be applied"),
        ):
            with self.subTest(fields=fields):
                response = self.apply(self.body(preview, fields))
                self.assertEqual(response.status_code, 400)
                self.assertIn(text, response.data["detail"])
        for fields in ([], ["Title; DROP"], ["x" * 80]):
            with self.subTest(fields=fields):
                self.assertEqual(self.apply(self.body(preview, fields)).status_code, 400)
        self.assertNothingWritten(before)

    def test_locked_field_cannot_be_applied(self):
        CanonicalFieldState.objects.create(
            target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
            target_id=self.movie.id,
            field_name="tagline",
            source=CanonicalFieldState.Source.MANUAL,
            locked=True,
        )
        preview = self.preview()
        response = self.apply(self.body(preview, ["tagline"]))
        self.assertEqual(response.status_code, 400)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.tagline, "")

    def test_stale_target_is_refused(self):
        preview = self.preview()
        self.movie.tagline = "Edited elsewhere"
        self.movie.save()
        before = self.catalog_snapshot()
        response = self.apply(self.body(preview, ["studios"]))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "target_changed")
        self.assertNothingWritten(before)

    def test_new_lock_after_review_is_refused(self):
        preview = self.preview()
        CanonicalFieldState.objects.create(
            target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
            target_id=self.movie.id,
            field_name="studios",
            source=CanonicalFieldState.Source.MANUAL,
            locked=True,
        )
        response = self.apply(self.body(preview, ["tagline"]))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "target_changed")

    def test_changed_provider_data_is_refused(self):
        preview = self.preview()
        cache.clear()
        self.detail = {**MOVIE_DETAIL, "tagline": "A different tagline."}
        before = self.catalog_snapshot()
        response = self.apply(self.body(preview, ["tagline"]))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "provider_changed")
        self.assertNothingWritten(before)

    def test_tampered_fingerprints_are_refused(self):
        preview = self.preview()
        for key in ("target_revision", "provider_snapshot"):
            with self.subTest(key=key):
                response = self.apply(self.body(preview, ["tagline"], **{key: "0" * 64}))
                self.assertEqual(response.status_code, 409)
                response = self.apply(self.body(preview, ["tagline"], **{key: "not-a-hash"}))
                self.assertEqual(response.status_code, 400)

    def test_ownership_and_authentication(self):
        from libraries.models import Library
        from media.models import MediaItem

        preview = self.preview()
        theirs_library = Library.objects.create(owner=self.other, name="Theirs", path="/t", content_type="movies")
        theirs = MediaItem.objects.create(library=theirs_library, title="The Matrix", media_type=MediaItem.MediaType.MOVIE)
        self.assertEqual(self.apply(self.body(preview, ["tagline"]), target=theirs).status_code, 404)
        self.client.force_authenticate(None)
        self.assertIn(self.apply(self.body(preview, ["tagline"])).status_code, (401, 403))

    def test_csrf_is_enforced_for_session_logins(self):
        preview = self.preview()
        client = APIClient(enforce_csrf_checks=True)
        self.assertTrue(client.login(email="owner@example.com", password="password"))
        response = client.post(self.url("movie", self.movie.id, "apply"), self.body(preview, ["tagline"]), format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(MetadataChangeSet.objects.count(), 0)

    def test_failure_inside_transaction_rolls_everything_back(self):
        preview = self.preview()
        before = self.catalog_snapshot()
        with (
            patch("metadata.services.provider_apply.MetadataChangeSet.objects.create", side_effect=RuntimeError("boom")),
            self.assertRaises(RuntimeError),
        ):
            self.apply(self.body(preview, ["tagline", "studios"]))
        self.assertNothingWritten(before)


class IdempotencyTests(_ApplyTestCase):
    def test_repeated_submission_returns_recorded_result(self):
        preview = self.preview()
        body = self.body(preview, ["tagline", "genres"])
        first = self.apply(body)
        second = self.apply(body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["replayed"])
        self.assertEqual(second.data["change_set"]["id"], first.data["change_set"]["id"])
        self.assertEqual(MetadataChangeSet.objects.count(), 1)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.genres, ["Action", "Science Fiction"])

    def test_reused_operation_id_with_different_plan_fails(self):
        preview = self.preview()
        body = self.body(preview, ["tagline"])
        self.assertEqual(self.apply(body).status_code, 200)
        response = self.apply({**body, "fields": ["studios"]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "operation_reused")
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.studios, [])

    def test_operation_id_cannot_cross_targets(self):
        preview = self.preview()
        body = self.body(preview, ["tagline"])
        self.assertEqual(self.apply(body).status_code, 200)
        series_preview = self.preview(kind="series")
        response = self.apply(
            self.body(series_preview, ["end_year"], operation_id=body["operation_id"]), kind="series"
        )
        self.assertEqual(response.status_code, 409)


class ProvenanceBehaviourTests(_ApplyTestCase):
    def test_provider_values_survive_scans_but_not_manual_locks(self):
        preview = self.preview()
        self.assertEqual(self.apply(self.body(preview, ["tagline"])).status_code, 200)

        # Library scans skip locked fields, so provider values are protected.
        self.assertTrue(
            is_field_locked(target_type="media_item", target_id=self.movie.id, field_name="tagline")
        )
        set_field_provenance(
            target_type="media_item", target_id=self.movie.id, field_name="tagline", source="nfo", value="From NFO"
        )
        self.assertEqual(self.states()["tagline"].source, CanonicalFieldState.Source.PROVIDER)

        # A later reviewed match may replace a provider value.
        cache.clear()
        self.detail = {**MOVIE_DETAIL, "tagline": "Free your mind."}
        rows = {row["field"]: row for row in self.preview()["fields"]}
        self.assertEqual(rows["tagline"]["status"], "different")
        self.assertTrue(rows["tagline"]["selectable"])
        self.assertEqual(rows["tagline"]["current_source"], "provider")

        # A manual edit takes precedence again.
        state = self.states()["tagline"]
        state.source = CanonicalFieldState.Source.MANUAL
        state.save()
        rows = {row["field"]: row for row in self.preview()["fields"]}
        self.assertEqual(rows["tagline"]["status"], "locked")

    def test_history_lists_provider_change(self):
        preview = self.preview()
        self.apply(self.body(preview, ["tagline"]))
        history = serialize_history(target_type="media_item", target_id=self.movie.id)
        self.assertEqual(history[0]["source_label"], "Metadata Provider")
        self.assertEqual(history[0]["note"], "Applied from TMDB (603).")
