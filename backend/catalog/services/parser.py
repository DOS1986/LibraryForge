import re

from dataclasses import (
    asdict,
    dataclass,
)

from pathlib import PurePosixPath

from django.utils.text import slugify


DECORATIVE_TRAILING_YEAR_RE = re.compile(
    r"^(?P<title>.*?\S)\s*"
    r"(?:"
    r"[\(\[](?P<bracket_year>(?:19|20)\d{2})[\)\]]"
    r"|"
    r"[\s._-]+(?P<plain_year>(?:19|20)\d{2})"
    r")"
    r"\s*$"
)

IDENTITY_SEPARATOR_RE = re.compile(
    r"[\\/+|:]+"
)

IDENTITY_PUNCTUATION_RE = re.compile(
    r"[^\w\s-]+",
    re.UNICODE,
)

SEASON_FOLDER_RE = re.compile(
    r"^(?:season[\s._-]*(?P<season>\d{1,3})|s(?P<short>\d{1,3}))$",
    re.IGNORECASE,
)

SPECIALS_RE = re.compile(
    r"^(?:specials?|extras?)$",
    re.IGNORECASE,
)

SXXEXX_RE = re.compile(
    r"(?i)(?P<token>"
    r"s(?P<season>\d{1,3})"
    r"e(?P<episode>\d{1,3})"
    r"(?:[\s._-]*e(?P<episode_end>\d{1,3}))?"
    r")"
)

X_RE = re.compile(
    r"(?i)(?P<token>"
    r"(?P<season>\d{1,3})"
    r"x"
    r"(?P<episode>\d{1,3})"
    r"(?:[\s._-]*x(?P<episode_end>\d{1,3}))?"
    r")"
)

QUALITY_TOKENS = (
    "2160p",
    "1080p",
    "720p",
    "576p",
    "480p",
    "uhd",
    "bluray",
    "blu-ray",
    "bdrip",
    "web-dl",
    "webdl",
    "webrip",
    "hdtv",
    "remux",
    "x264",
    "x265",
    "h264",
    "h265",
    "hevc",
    "av1",
    "aac",
    "dts",
    "truehd",
    "atmos",
)

EDITION_PATTERNS = (
    (
        re.compile(
            r"\bfinal[\s._-]*cut\b",
            re.IGNORECASE,
        ),
        "Final Cut",
    ),
    (
        re.compile(
            r"\bdirector'?s[\s._-]*cut\b",
            re.IGNORECASE,
        ),
        "Director's Cut",
    ),
    (
        re.compile(
            r"\bextended(?:[\s._-]*cut)?\b",
            re.IGNORECASE,
        ),
        "Extended",
    ),
    (
        re.compile(
            r"\btheatrical(?:[\s._-]*cut)?\b",
            re.IGNORECASE,
        ),
        "Theatrical",
    ),
    (
        re.compile(
            r"\bunrated\b",
            re.IGNORECASE,
        ),
        "Unrated",
    ),
    (
        re.compile(
            r"\bremaster(?:ed)?\b",
            re.IGNORECASE,
        ),
        "Remastered",
    ),
)


@dataclass
class SemanticCandidate:
    kind: str = "unknown"

    title: str = ""
    year: int | None = None

    series_title: str = ""
    series_year: int | None = None

    season_number: int | None = None
    episode_number: int | None = None
    episode_end_number: int | None = None
    episode_title: str = ""

    edition: str = ""

    source: str = ""
    confidence: float = 0.0

    def to_dict(self):
        return asdict(
            self
        )


def semantic_slug(
    value: str,
):
    result = slugify(
        value
    )

    return (
        result
        or "untitled"
    )



def identity_text_key(
    value: str,
):
    """
    Normalize display text only for semantic identity comparison.

    This deliberately treats common filesystem-safe substitutions as
    equivalent without changing the canonical display title.

    Examples that compare equal:

        "Mr. Robot" == "Mr Robot"
        "Show/Name" == "Show+Name"
        "Law: Order" == "Law - Order"
        "Schitt's Creek" == "Schitts Creek"

    A year is NOT removed here. Year decoration is parsed separately so
    titles that are genuinely numeric are not accidentally merged.
    """

    value = (
        value
        or ""
    ).casefold()

    value = (
        IDENTITY_SEPARATOR_RE
        .sub(
            " ",
            value,
        )
    )

    value = value.replace(
        ".",
        " ",
    )

    value = re.sub(
        r"['’`]",
        "",
        value,
    )

    value = re.sub(
        r"[_-]+",
        " ",
        value,
    )

    value = (
        IDENTITY_PUNCTUATION_RE
        .sub(
            " ",
            value,
        )
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def _extract_decorative_trailing_year(
    value: str,
):
    """
    Extract a Jellyfin/folder-style trailing display year while preserving
    numeric titles such as "1883" or "1923".

    Examples:

        "The Expanse (2015)" -> ("The Expanse", 2015)
        "The Expanse [2015]" -> ("The Expanse", 2015)
        "The Expanse - 2015" -> ("The Expanse", 2015)
        "The Expanse 2015"   -> ("The Expanse", 2015)
        "1923"               -> ("1923", None)
    """

    raw = (
        value
        or ""
    ).strip()

    match = (
        DECORATIVE_TRAILING_YEAR_RE
        .match(
            raw
        )
    )

    if not match:
        return (
            raw,
            None,
        )

    title = (
        match.group(
            "title"
        )
        .strip(
            " -_."
        )
    )

    year_text = (
        match.group(
            "bracket_year"
        )
        or match.group(
            "plain_year"
        )
    )

    if not title:
        return (
            raw,
            None,
        )

    return (
        title,
        int(
            year_text
        ),
    )


def series_semantic_key(
    title: str,
    year: int | None,
):
    return (
        "series:"
        f"{semantic_slug(title)}:"
        f"{year or 'unknown'}"
    )


def movie_semantic_key(
    title: str,
    year: int | None,
):
    return (
        "movie:"
        f"{semantic_slug(title)}:"
        f"{year or 'unknown'}"
    )


def episode_semantic_key(
    series_key: str,
    season_number: int,
    episode_number: int,
):
    return (
        "episode:"
        f"{series_key}:"
        f"s{season_number:04d}"
        f"e{episode_number:04d}"
    )


def _humanize(
    value: str,
):
    value = re.sub(
        r"[\[\]\(\)]",
        " ",
        value,
    )

    value = re.sub(
        r"[._]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip(
        " -_"
    )


def _remove_quality_tokens(
    value: str,
):
    result = value

    for token in QUALITY_TOKENS:
        result = re.sub(
            rf"(?i)\b{re.escape(token)}\b",
            " ",
            result,
        )

    return _humanize(
        result
    )


def _extract_edition(
    value: str,
):
    for (
        pattern,
        edition,
    ) in EDITION_PATTERNS:
        if pattern.search(
            value
        ):
            return (
                edition,
                pattern.sub(
                    " ",
                    value,
                ),
            )

    return (
        "",
        value,
    )


def _clean_title(
    value: str,
):
    return _remove_quality_tokens(
        _humanize(
            value
        )
    )


def _series_from_path(
    relative_path: str,
    filename_prefix: str,
):
    path = PurePosixPath(
        relative_path
    )

    parent = path.parent

    if (
        parent.name
        and (
            SEASON_FOLDER_RE.match(
                parent.name
            )
            or SPECIALS_RE.match(
                parent.name
            )
        )
    ):
        series_raw = (
            parent.parent.name
        )

    elif (
        parent.name
        and str(
            parent
        ) != "."
    ):
        series_raw = (
            parent.name
        )

    else:
        series_raw = (
            filename_prefix
        )

    series_identity = (
        _remove_quality_tokens(
            series_raw
        )
    )

    (
        series_without_year,
        series_year,
    ) = (
        _extract_decorative_trailing_year(
            series_identity
        )
    )

    series_title = _clean_title(
        series_without_year
    )

    if not series_title:
        series_title = _clean_title(
            filename_prefix
        )

    return (
        series_title,
        series_year,
    )


def _parse_episode(
    relative_path: str,
):
    path = PurePosixPath(
        relative_path
    )

    stem = path.stem

    match = (
        SXXEXX_RE.search(
            stem
        )
        or X_RE.search(
            stem
        )
    )

    if not match:
        return None

    season = int(
        match.group(
            "season"
        )
    )

    episode = int(
        match.group(
            "episode"
        )
    )

    episode_end = (
        int(
            match.group(
                "episode_end"
            )
        )
        if (
            match.group(
                "episode_end"
            )
        )
        else None
    )

    prefix = stem[
        :match.start()
    ]

    suffix = stem[
        match.end():
    ]

    (
        series_title,
        series_year,
    ) = _series_from_path(
        relative_path,
        prefix,
    )

    episode_title = (
        _clean_title(
            suffix
        )
    )

    confidence = 0.92

    if (
        path.parent.name
        and (
            SEASON_FOLDER_RE.match(
                path.parent.name
            )
            or SPECIALS_RE.match(
                path.parent.name
            )
        )
    ):
        confidence = 0.97

    return SemanticCandidate(
        kind="episode",
        series_title=series_title,
        series_year=series_year,
        season_number=season,
        episode_number=episode,
        episode_end_number=(
            episode_end
        ),
        episode_title=(
            episode_title
        ),
        title=(
            episode_title
            or (
                "Episode "
                f"{episode}"
            )
        ),
        source="filename",
        confidence=confidence,
    )


def _movie_source_name(
    relative_path: str,
):
    path = PurePosixPath(
        relative_path
    )

    if (
        len(path.parts)
        > 1
        and path.parent.name
    ):
        return path.parent.name

    return path.stem


def _parse_movie(
    relative_path: str,
):
    path = PurePosixPath(
        relative_path
    )

    raw = _movie_source_name(
        relative_path
    )

    (
        edition,
        _filename_without_edition,
    ) = _extract_edition(
        path.stem
    )

    (
        _identity_edition,
        without_edition,
    ) = _extract_edition(
        raw
    )

    # Remove release/quality tokens before looking for the display year.
    #
    # This is critical for numeric movie titles:
    #
    #     2067 (2020).mkv
    #     1917 (2019).mkv
    #     1923.mkv
    #
    # The movie year is the trailing decorative year, not the first
    # four-digit number found anywhere in the title.
    identity_text = (
        _remove_quality_tokens(
            without_edition
        )
    )

    (
        without_year,
        year,
    ) = (
        _extract_decorative_trailing_year(
            identity_text
        )
    )

    # If a movie lives in a generic parent folder, the useful year may be
    # present only in the filename. Apply the same safe trailing-year logic
    # there rather than falling back to the old first-four-digit matcher.
    if year is None:
        (
            _filename_edition,
            filename_without_edition,
        ) = _extract_edition(
            path.stem
        )

        filename_identity = (
            _remove_quality_tokens(
                filename_without_edition
            )
        )

        (
            filename_without_year,
            filename_year,
        ) = (
            _extract_decorative_trailing_year(
                filename_identity
            )
        )

        if filename_year is not None:
            year = filename_year

            # Use the filename title only when the current source was the
            # filename itself. If we have a meaningful movie folder, preserve
            # the folder-derived title and use only the filename year.
            if raw == path.stem:
                without_year = (
                    filename_without_year
                )

    title = _clean_title(
        without_year
    )

    if not title:
        return SemanticCandidate()

    confidence = (
        0.94
        if year
        else 0.72
    )

    return SemanticCandidate(
        kind="movie",
        title=title,
        year=year,
        edition=edition,
        source="folder",
        confidence=confidence,
    )


def parse_filename_candidate(
    *,
    relative_path: str,
    library_content_type: str,
):
    episode = _parse_episode(
        relative_path
    )

    if episode:
        if (
            library_content_type
            in {
                "movies",
            }
        ):
            episode.confidence = (
                min(
                    episode.confidence,
                    0.55,
                )
            )

        return episode

    if (
        library_content_type
        in {
            "movies",
            "mixed",
            "auto",
        }
    ):
        return _parse_movie(
            relative_path
        )

    return SemanticCandidate()


def _root_data(
    nfo_file,
):
    if not nfo_file:
        return (
            "",
            {},
        )

    root_name = (
        nfo_file.root_element
        or ""
    ).lower()

    parsed = (
        nfo_file.parsed_data
        or {}
    )

    root_data = (
        parsed.get(
            nfo_file.root_element
        )
        or parsed.get(
            root_name
        )
        or {}
    )

    if not isinstance(
        root_data,
        dict,
    ):
        root_data = {}

    return (
        root_name,
        root_data,
    )


def _int_value(
    value,
):
    if isinstance(
        value,
        list,
    ):
        value = (
            value[0]
            if value
            else None
        )

    if value in (
        None,
        "",
    ):
        return None

    try:
        return int(
            str(value)
            .strip()
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def parse_nfo_candidate(
    nfo_file,
):
    (
        root_name,
        data,
    ) = _root_data(
        nfo_file
    )

    if root_name == "movie":
        raw_title = (
            str(
                data.get(
                    "title",
                    "",
                )
            )
            .strip()
        )

        (
            title,
            title_year,
        ) = (
            _extract_decorative_trailing_year(
                raw_title
            )
        )

        year = (
            _int_value(
                data.get(
                    "year"
                )
            )
            or title_year
        )

        if not title:
            return SemanticCandidate()

        return SemanticCandidate(
            kind="movie",
            title=title,
            year=year,
            source="nfo",
            confidence=0.995,
        )

    if (
        root_name
        == "episodedetails"
    ):
        raw_series_title = (
            str(
                data.get(
                    "showtitle",
                    "",
                )
            )
            .strip()
        )

        (
            series_title,
            series_year,
        ) = (
            _extract_decorative_trailing_year(
                raw_series_title
            )
        )

        episode_title = (
            str(
                data.get(
                    "title",
                    "",
                )
            )
            .strip()
        )

        season = _int_value(
            data.get(
                "season"
            )
        )

        episode = _int_value(
            data.get(
                "episode"
            )
        )

        if (
            not series_title
            or season is None
            or episode is None
        ):
            return SemanticCandidate()

        return SemanticCandidate(
            kind="episode",
            title=(
                episode_title
                or (
                    "Episode "
                    f"{episode}"
                )
            ),
            series_title=(
                series_title
            ),
            series_year=(
                series_year
            ),
            season_number=season,
            episode_number=episode,
            episode_title=(
                episode_title
            ),
            source="nfo",
            confidence=0.995,
        )

    return SemanticCandidate()


def identities_conflict(
    first: SemanticCandidate,
    second: SemanticCandidate,
):
    """
    Determine whether two candidates identify different logical media.

    Descriptive title formatting is intentionally NOT an identity conflict.
    In particular, episode display-title punctuation does not matter because
    Series + Season + Episode is the episode identity.

    Series/movie title comparison tolerates common filesystem-safe
    substitutions such as dot removal and slash -> plus.
    """

    if (
        first.kind == "unknown"
        or second.kind == "unknown"
    ):
        return False

    if first.kind != second.kind:
        return True

    if first.kind == "movie":
        if (
            identity_text_key(
                first.title
            )
            != identity_text_key(
                second.title
            )
        ):
            return True

        if (
            first.year
            and second.year
            and first.year
            != second.year
        ):
            return True

        return False

    if first.kind == "episode":
        if (
            identity_text_key(
                first.series_title
            )
            != identity_text_key(
                second.series_title
            )
        ):
            return True

        if (
            first.series_year
            and second.series_year
            and first.series_year
            != second.series_year
        ):
            return True

        return (
            first.season_number
            != second.season_number
            or first.episode_number
            != second.episode_number
        )

    return False


def build_version_name(
    media_file,
):
    height = (
        media_file.height
        or 0
    )

    if height >= 2000:
        resolution = "2160p"

    elif height >= 1000:
        resolution = "1080p"

    elif height >= 700:
        resolution = "720p"

    elif height:
        resolution = (
            f"{height}p"
        )

    else:
        resolution = ""

    codec = (
        media_file.video_codec
        or ""
    ).upper()

    parts = [
        value
        for value
        in (
            resolution,
            codec,
        )
        if value
    ]

    return (
        " ".join(
            parts
        )
        or "Default"
    )
