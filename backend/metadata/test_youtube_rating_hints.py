"""Channel rating hints from YouTube's made-for-kids and age-restriction flags."""

from datetime import date, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.test import SimpleTestCase

from catalog.models import CanonicalFieldState, Channel, MetadataChangeSet, OnlineVideo
from integrations.models import LibraryIntegration
from integrations.providers.http import ProviderHttpError
from libraries.models import Library
from media.models import MediaItem
from metadata.services.youtube_rating_hints import MAX_VIDEOS_PER_CHANNEL, hint_for
from metadata.test_provider_match import _MatchApiTestCase


class HintRuleTests(SimpleTestCase):
    def test_age_restricted_video_wins(self):
        hint = hint_for({"made_for_kids": True}, [{"made_for_kids": False, "age_restricted": True}])
        self.assertEqual((hint["status"], hint["rating"]), ("hint", "TV-MA"))

    def test_made_for_kids_channel(self):
        hint = hint_for({"made_for_kids": True}, [])
        self.assertEqual(hint["rating"], "TV-Y")
        self.assertIn("TV-Y7", hint["note"])

    def test_mostly_kids_videos(self):
        videos = [{"made_for_kids": True}] * 9 + [{"made_for_kids": False}]
        self.assertEqual(hint_for({"made_for_kids": False}, videos)["rating"], "TV-Y")

    def test_general_audience_has_no_hint(self):
        videos = [{"made_for_kids": True}] * 8 + [{"made_for_kids": False}] * 2
        hint = hint_for({"made_for_kids": None}, videos)
        self.assertEqual((hint["status"], hint["rating"]), ("no_signal", ""))
        self.assertIn("8 of 10", hint["reason"])

    def test_nothing_found(self):
        self.assertEqual(hint_for(None, [])["status"], "not_found")


class _HintApiBase(_MatchApiTestCase):
    def setUp(self):
        super().setUp()
        self.youtube = Library.objects.create(owner=self.user, name="Youtube", path="/yt", content_type="online_video")
        self.yt_connection = self._connection(self.user, "My YouTube", provider="youtube")
        LibraryIntegration.objects.create(library=self.youtube, connection=self.yt_connection, capabilities=["metadata"])
        self.kids = Channel.objects.create(library=self.youtube, provider="youtube", source_id="UCkids", title="Kids")
        self.mature = Channel.objects.create(library=self.youtube, provider="youtube", source_id="UCmature", title="Mature")
        self.general = Channel.objects.create(library=self.youtube, provider="youtube", source_id="UCgen", title="General")
        self.channel_flags = {"UCkids": True, "UCmature": False, "UCgen": False}
        self.video_flags: dict[str, tuple[bool, bool]] = {}
        self._video(self.mature, "v-mature-1", kids=False, adult=True)
        self._video(self.mature, "v-mature-2", kids=False, adult=False)
        self._video(self.general, "v-gen-1", kids=False, adult=False)

        yt_patch = patch("integrations.providers.youtube.request_json", side_effect=self._respond)
        self.yt_request = yt_patch.start()
        self.addCleanup(yt_patch.stop)

    def _video(self, channel, source_id, *, kids, adult, day=0):
        item = MediaItem.objects.create(library=self.youtube, title=source_id, media_type=MediaItem.MediaType.ONLINE_VIDEO)
        OnlineVideo.objects.create(
            library=self.youtube,
            media_item=item,
            channel=channel,
            provider="youtube",
            source_id=source_id,
            upload_date=date(2024, 1, 1) + timedelta(days=day),
        )
        self.video_flags[source_id] = (kids, adult)

    def _respond(self, url, **kwargs):
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        ids = query["id"][0].split(",")
        if parsed.path.endswith("/channels"):
            items = [
                {"id": value, "status": {"madeForKids": self.channel_flags[value]}}
                for value in ids
                if value in self.channel_flags
            ]
        else:
            items = []
            for value in ids:
                if value not in self.video_flags:
                    continue
                kids, adult = self.video_flags[value]
                item = {"id": value, "status": {"madeForKids": kids}, "contentDetails": {"contentRating": {}}}
                if adult:
                    item["contentDetails"]["contentRating"]["ytRating"] = "ytAgeRestricted"
                items.append(item)
        return {"items": items}

    def url(self, library=None):
        return f"/api/libraries/{(library or self.youtube).id}/ratings/youtube-hints/"

    def hints(self, *channels, library=None):
        return self.client.get(self.url(library), {"ids": ",".join(str(channel.id) for channel in channels)})


class HintApiTests(_HintApiBase):
    def test_hints_per_channel(self):
        response = self.hints(self.kids, self.mature, self.general)

        self.assertEqual(response.status_code, 200, response.data)
        results = {row["title"]: row for row in response.data["results"]}
        self.assertEqual((results["Kids"]["rating"], results["Kids"]["action"]), ("TV-Y", "set"))
        self.assertEqual(results["Mature"]["rating"], "TV-MA")
        self.assertEqual(results["Mature"]["stats"]["videos_age_restricted"], 1)
        self.assertEqual((results["General"]["status"], results["General"]["action"]), ("no_signal", None))
        self.assertEqual(response.data["connection"]["provider"], "youtube")
        # Hints never write anything.
        self.kids.refresh_from_db()
        self.assertEqual(self.kids.content_rating, "")

    def test_channel_rating_reports_youtube_hints(self):
        response = self.client.get(f"/api/libraries/{self.youtube.id}/ratings/", {"kind": "channel"})
        kinds = {row["kind"]: row for row in response.data["kinds"]}
        self.assertTrue(kinds["channel"]["youtube_hints"])

    def test_videos_are_batched_and_capped(self):
        for index in range(MAX_VIDEOS_PER_CHANNEL + 10):
            self._video(self.general, f"bulk-{index}", kids=True, adult=False, day=index + 1)

        response = self.hints(self.general)

        self.assertEqual(response.status_code, 200)
        row = response.data["results"][0]
        self.assertEqual(row["stats"]["videos_checked"], MAX_VIDEOS_PER_CHANNEL)
        # The newest videos are checked, and they're all made for kids.
        self.assertEqual(row["rating"], "TV-Y")
        video_calls = [call for call in self.yt_request.call_args_list if "/videos?" in call.args[0]]
        self.assertEqual(len(video_calls), MAX_VIDEOS_PER_CHANNEL // 50)
        for call in video_calls:
            self.assertLessEqual(len(parse_qs(urlparse(call.args[0]).query)["id"][0].split(",")), 50)

    def test_results_are_cached(self):
        self.hints(self.mature)
        calls = self.yt_request.call_count
        self.hints(self.mature)
        self.assertEqual(self.yt_request.call_count, calls)

    def test_needs_a_youtube_connection_on_the_library(self):
        LibraryIntegration.objects.filter(library=self.youtube).delete()
        response = self.hints(self.kids)
        self.assertEqual(response.status_code, 409)
        self.assertIn("YouTube connection", response.data["detail"])

    def test_quota_errors_are_explained(self):
        self.yt_request.side_effect = ProviderHttpError("forbidden", 403)
        response = self.hints(self.kids)
        self.assertEqual(response.status_code, 502, response.data)
        self.assertIn("quota", str(response.data))

    def test_other_users_library_is_hidden(self):
        theirs = Library.objects.create(owner=self.other, name="Theirs", path="/t", content_type="online_video")
        self.assertEqual(self.hints(self.kids, library=theirs).status_code, 404)

    def test_channels_from_another_library_are_rejected(self):
        elsewhere = Channel.objects.create(library=self.library, provider="youtube", source_id="UCx", title="X")
        self.assertEqual(self.hints(elsewhere).status_code, 404)

    def test_too_many_or_bad_ids(self):
        self.assertEqual(self.client.get(self.url(), {"ids": "nope"}).status_code, 400)


class ApplyHintTests(_HintApiBase):
    def apply(self, hints):
        return self.client.post(
            self.url(), {"hints": {str(channel.id): rating for channel, rating in hints}}, format="json"
        )

    def test_apply_writes_with_provider_provenance(self):
        response = self.apply([(self.kids, "TV-Y"), (self.mature, "TV-MA")])

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["counts"]["applied"], 2)
        self.kids.refresh_from_db()
        self.assertEqual(self.kids.content_rating, "TV-Y")
        state = CanonicalFieldState.objects.get(
            target_type=CanonicalFieldState.TargetType.CHANNEL, target_id=self.kids.id, field_name="content_rating"
        )
        self.assertEqual(
            (state.source, state.source_ref, state.locked),
            (CanonicalFieldState.Source.PROVIDER, "youtube:channel:UCkids", True),
        )
        change = MetadataChangeSet.objects.get(target_id=self.kids.id)
        self.assertEqual(change.source, MetadataChangeSet.Source.PROVIDER)
        self.assertEqual(change.changes["content_rating"], {"old": "", "new": "TV-Y"})
        self.assertTrue(change.details["hint"])

        again = self.apply([(self.kids, "TV-Y")])
        self.assertEqual(again.data["counts"]["unchanged"], 1)
        self.assertEqual(MetadataChangeSet.objects.filter(target_id=self.kids.id).count(), 1)

    def test_changed_hint_is_not_applied(self):
        self.channel_flags["UCkids"] = False

        response = self.apply([(self.kids, "TV-Y")])

        self.assertEqual(response.data["counts"]["changed"], 1)
        self.kids.refresh_from_db()
        self.assertEqual(self.kids.content_rating, "")

    def test_a_different_rating_than_the_hint_is_refused(self):
        response = self.apply([(self.kids, "TV-MA")])
        self.assertEqual(response.data["counts"]["changed"], 1)

    def test_manual_rating_is_never_replaced(self):
        self.client.post(
            f"/api/libraries/{self.youtube.id}/ratings/set/",
            {"kind": "channel", "ids": [str(self.kids.id)], "rating": "TV-Y7"},
            format="json",
        )

        preview = self.hints(self.kids).data["results"][0]
        self.assertEqual(preview["action"], "locked")
        response = self.apply([(self.kids, "TV-Y")])

        self.assertEqual(response.data["counts"]["locked"], 1)
        self.kids.refresh_from_db()
        self.assertEqual(self.kids.content_rating, "TV-Y7")

    def test_a_previous_hint_can_be_updated(self):
        self.apply([(self.kids, "TV-Y")])
        self.channel_flags["UCkids"] = False
        self._video(self.kids, "v-kids-adult", kids=False, adult=True)
        from django.core.cache import cache

        cache.clear()

        preview = self.hints(self.kids).data["results"][0]
        self.assertEqual((preview["rating"], preview["action"]), ("TV-MA", "change"))
        self.assertEqual(self.apply([(self.kids, "TV-MA")]).data["counts"]["applied"], 1)

    def test_apply_needs_hints(self):
        self.assertEqual(self.client.post(self.url(), {"hints": []}, format="json").status_code, 400)
