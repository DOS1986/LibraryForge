from rest_framework import (
    filters,
    permissions,
    status,
    viewsets,
)

from rest_framework.decorators import (
    action,
)

from rest_framework.exceptions import (
    ValidationError,
)

from rest_framework.response import (
    Response,
)

from libraryforge.pagination import (
    LibraryForgePagination,
)

from catalog.models import (
    Episode,
    Season,
    SemanticMatch,
    Series,
)

from catalog.serializers import (
    EpisodeCatalogSerializer,
    MovieCatalogSerializer,
    SeasonCatalogSerializer,
    SemanticLockRequestSerializer,
    SemanticMatchSerializer,
    SemanticResolveRequestSerializer,
    SeriesCatalogSerializer,
)

from catalog.services.parser import (
    SemanticCandidate,
)

from catalog.services.resolver import (
    apply_manual_resolution,
    get_match_candidate,
    reset_semantic_match,
    set_semantic_match_lock,
)

from catalog.services.online_video import (
    apply_manual_online_video_resolution,
    online_video_candidate_from_match,
)

from catalog.services.provenance import (
    semantic_match_provenance,
)

from media.models import MediaItem


class MovieCatalogViewSet(
    viewsets.ReadOnlyModelViewSet
):
    serializer_class = (
        MovieCatalogSerializer
    )

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = (
        LibraryForgePagination
    )

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    search_fields = [
        "title",
        "semantic_key",
    ]

    ordering_fields = [
        "title",
        "created_at",
        "updated_at",
    ]

    ordering = [
        "title",
    ]

    def get_queryset(self):
        queryset = (
            MediaItem.objects
            .filter(
                library__owner=(
                    self.request.user
                ),
                media_type=(
                    MediaItem
                    .MediaType
                    .MOVIE
                ),
                semantic_key__gt="",
                versions__media_file__is_present=True,
            )
            .distinct()
            .prefetch_related(
                "versions__media_file"
            )
        )

        library_id = (
            self.request
            .query_params
            .get(
                "library"
            )
        )

        if library_id:
            queryset = queryset.filter(
                library_id=library_id
            )

        return queryset


class SeriesCatalogViewSet(
    viewsets.ReadOnlyModelViewSet
):
    serializer_class = (
        SeriesCatalogSerializer
    )

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = (
        LibraryForgePagination
    )

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    search_fields = [
        "title",
        "sort_title",
        "semantic_key",
    ]

    ordering_fields = [
        "title",
        "sort_title",
        "start_year",
        "created_at",
        "updated_at",
    ]

    ordering = [
        "sort_title",
        "title",
    ]

    def get_queryset(self):
        queryset = (
            Series.objects
            .filter(
                library__owner=(
                    self.request.user
                ),
                seasons__episodes__media_item__versions__media_file__is_present=True,
            )
            .distinct()
            .prefetch_related(
                "seasons",
            )
        )

        library_id = (
            self.request
            .query_params
            .get(
                "library"
            )
        )

        if library_id:
            queryset = queryset.filter(
                library_id=library_id
            )

        return queryset


class SeasonCatalogViewSet(
    viewsets.ReadOnlyModelViewSet
):
    serializer_class = (
        SeasonCatalogSerializer
    )

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = (
        LibraryForgePagination
    )

    filter_backends = [
        filters.OrderingFilter,
    ]

    ordering_fields = [
        "season_number",
        "title",
    ]

    ordering = [
        "season_number",
    ]

    def get_queryset(self):
        queryset = (
            Season.objects
            .filter(
                series__library__owner=(
                    self.request.user
                ),
                episodes__media_item__versions__media_file__is_present=True,
            )
            .distinct()
            .select_related(
                "series"
            )
            .prefetch_related(
                "episodes"
            )
        )

        series_id = (
            self.request
            .query_params
            .get(
                "series"
            )
        )

        if series_id:
            queryset = queryset.filter(
                series_id=series_id
            )

        return queryset


class EpisodeCatalogViewSet(
    viewsets.ReadOnlyModelViewSet
):
    serializer_class = (
        EpisodeCatalogSerializer
    )

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = (
        LibraryForgePagination
    )

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    search_fields = [
        "media_item__title",
        "media_item__semantic_key",
    ]

    ordering_fields = [
        "episode_number",
        "air_date",
        "media_item__title",
    ]

    ordering = [
        "episode_number",
    ]

    def get_queryset(self):
        queryset = (
            Episode.objects
            .filter(
                season__series__library__owner=(
                    self.request.user
                ),
                media_item__versions__media_file__is_present=True,
            )
            .distinct()
            .select_related(
                "media_item",
                "season",
                "season__series",
            )
            .prefetch_related(
                "media_item__versions__media_file"
            )
        )

        season_id = (
            self.request
            .query_params
            .get(
                "season"
            )
        )

        series_id = (
            self.request
            .query_params
            .get(
                "series"
            )
        )

        if season_id:
            queryset = queryset.filter(
                season_id=season_id
            )

        if series_id:
            queryset = queryset.filter(
                season__series_id=(
                    series_id
                )
            )

        return queryset


class SemanticMatchViewSet(
    viewsets.ReadOnlyModelViewSet
):
    serializer_class = (
        SemanticMatchSerializer
    )

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = (
        LibraryForgePagination
    )

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    search_fields = [
        "media_file__file_name",
        "media_file__relative_path",
        "media_file__media_item__title",
        "notes",
    ]

    ordering_fields = [
        "status",
        "confidence",
        "locked",
        "last_resolved_at",
        "updated_at",
        "media_file__relative_path",
    ]

    ordering = [
        "status",
        "media_file__relative_path",
    ]

    def get_queryset(self):
        queryset = (
            SemanticMatch.objects
            .filter(
                media_file__library__owner=(
                    self.request.user
                )
            )
            .select_related(
                "media_file",
                "media_file__library",
                "media_file__media_item",
                "media_file__media_item__episode__season__series",
                "media_file__media_item__online_video__channel",
            )
        )

        library_id = (
            self.request
            .query_params
            .get(
                "library"
            )
        )

        match_status = (
            self.request
            .query_params
            .get(
                "status"
            )
        )

        locked = (
            self.request
            .query_params
            .get(
                "locked"
            )
        )

        attention = (
            self.request
            .query_params
            .get(
                "attention"
            )
        )

        if library_id:
            queryset = queryset.filter(
                media_file__library_id=(
                    library_id
                )
            )

        if match_status:
            queryset = queryset.filter(
                status=match_status
            )

        if (
            locked is not None
            and locked != ""
        ):
            normalized = (
                locked
                .strip()
                .lower()
            )

            if normalized in {
                "true",
                "1",
                "yes",
            }:
                queryset = queryset.filter(
                    locked=True
                )

            elif normalized in {
                "false",
                "0",
                "no",
            }:
                queryset = queryset.filter(
                    locked=False
                )

            else:
                raise ValidationError(
                    {
                        "locked":
                            (
                                "Use true or false."
                            )
                    }
                )

        if (
            attention
            and attention
            .strip()
            .lower()
            in {
                "true",
                "1",
                "yes",
            }
        ):
            queryset = queryset.filter(
                status__in=[
                    SemanticMatch
                    .Status
                    .UNRESOLVED,

                    SemanticMatch
                    .Status
                    .CONFLICT,
                ]
            )

        return queryset

    @action(
        detail=True,
        methods=[
            "post",
        ],
        url_path="resolve",
    )
    def resolve_match(
        self,
        request,
        pk=None,
    ):
        match = self.get_object()

        request_serializer = SemanticResolveRequestSerializer(
            data=request.data
        )
        request_serializer.is_valid(raise_exception=True)
        data = request_serializer.validated_data
        candidate_source = data["candidate_source"]

        is_online_video = (
            match.media_file.library.content_type == "online_video"
            or data.get("kind") == "online_video"
            or (match.candidate_data or {}).get("kind") == "online_video"
        )

        if is_online_video:
            if candidate_source == "manual":
                candidate = {
                    "kind": "online_video",
                    "provider": data.get("provider", "").strip(),
                    "source_id": data.get("video_id", "").strip(),
                    "title": data.get("title", "").strip(),
                    "channel_id": data.get("channel_id", "").strip(),
                    "channel_title": data.get("channel_title", "").strip(),
                    "channel_handle": data.get("channel_handle", "").strip(),
                    "source_url": data.get("source_url", "").strip(),
                    "upload_date": data.get("upload_date"),
                    "video_kind": data.get("video_kind", "unknown"),
                }
            else:
                candidate = online_video_candidate_from_match(
                    match,
                    candidate_source,
                )

                if not candidate:
                    raise ValidationError({
                        "candidate_source": (
                            "That Online Video candidate is not available "
                            "for this item."
                        )
                    })

                # Confirming a detected identity must not silently turn
                # source-provided descriptive metadata into manual canonical
                # overrides. Keep this action identity-only; normal metadata
                # refresh/provenance continues to own title, artwork, tags, etc.
                candidate = {
                    "kind": "online_video",
                    "provider": candidate.get("provider", ""),
                    "source_id": candidate.get("source_id", ""),
                    "channel_id": candidate.get("channel_id", ""),
                }

            try:
                updated = apply_manual_online_video_resolution(
                    match=match,
                    candidate=candidate,
                    lock=data["lock"],
                    notes=data.get("notes", ""),
                    user=request.user,
                )
            except ValueError as exc:
                raise ValidationError({"detail": str(exc)}) from exc

        else:
            if candidate_source == "manual":
                kind = data["kind"]

                if kind == "movie":
                    candidate = SemanticCandidate(
                        kind="movie",
                        title=data["title"].strip(),
                        year=data.get("year"),
                        edition=data.get("edition", "").strip(),
                        source="manual",
                        confidence=1.0,
                    )
                else:
                    episode_title = data.get("episode_title", "").strip()
                    candidate = SemanticCandidate(
                        kind="episode",
                        title=(
                            episode_title
                            or f"Episode {data['episode_number']}"
                        ),
                        series_title=data["series_title"].strip(),
                        series_year=data.get("series_year"),
                        season_number=data["season_number"],
                        episode_number=data["episode_number"],
                        episode_end_number=data.get("episode_end_number"),
                        episode_title=episode_title,
                        source="manual",
                        confidence=1.0,
                    )
            else:
                candidate = get_match_candidate(match, candidate_source)

                if candidate.kind == "unknown":
                    raise ValidationError({
                        "candidate_source": (
                            "That candidate is not available for this item."
                        )
                    })

            try:
                updated = apply_manual_resolution(
                    match=match,
                    candidate=candidate,
                    lock=data["lock"],
                    notes=data.get("notes", ""),
                )
            except ValueError as exc:
                raise ValidationError({"detail": str(exc)}) from exc

        updated = self.get_queryset().get(pk=updated.pk)

        return Response(
            SemanticMatchSerializer(updated).data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["get"],
        url_path="provenance",
    )
    def provenance(
        self,
        request,
        pk=None,
    ):
        match = self.get_object()
        return Response(
            semantic_match_provenance(match),
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=[
            "post",
        ],
        url_path="set-lock",
    )
    def set_lock(
        self,
        request,
        pk=None,
    ):
        match = (
            self.get_object()
        )

        request_serializer = (
            SemanticLockRequestSerializer(
                data=request.data
            )
        )

        request_serializer.is_valid(
            raise_exception=True
        )

        updated = (
            set_semantic_match_lock(
                match=match,
                locked=(
                    request_serializer
                    .validated_data[
                        "locked"
                    ]
                ),
            )
        )

        updated = (
            self.get_queryset()
            .get(
                pk=updated.pk
            )
        )

        return Response(
            SemanticMatchSerializer(
                updated
            ).data
        )

    @action(
        detail=True,
        methods=[
            "post",
        ],
        url_path="reset",
    )
    def reset_match(
        self,
        request,
        pk=None,
    ):
        match = (
            self.get_object()
        )

        try:
            (
                updated,
                result,
            ) = reset_semantic_match(
                match=match
            )

        except ValueError as exc:
            raise ValidationError(
                {
                    "detail":
                        str(exc)
                }
            ) from exc

        updated = (
            self.get_queryset()
            .get(
                pk=updated.pk
            )
        )

        return Response(
            {
                "result":
                    result,

                "match":
                    SemanticMatchSerializer(
                        updated
                    ).data,
            }
        )

