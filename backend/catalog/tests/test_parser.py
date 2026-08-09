import pytest

from catalog.services.parser import (
    identities_conflict,
    identity_text_key,
    parse_filename_candidate,
    parse_nfo_candidate,
)


@pytest.mark.parametrize(
    (
        "relative_path",
        "series",
        "season",
        "episode",
    ),
    [
        (
            (
                "The Expanse/"
                "Season 01/"
                "The Expanse - "
                "S01E01 - Dulcinea.mkv"
            ),
            "The Expanse",
            1,
            1,
        ),
        (
            (
                "The Expanse/"
                "Season 02/"
                "The.Expanse.S02E03."
                "1080p.WEB-DL.mkv"
            ),
            "The Expanse",
            2,
            3,
        ),
        (
            "The Expanse/The Expanse 3x04.mkv",
            "The Expanse",
            3,
            4,
        ),
    ],
)
def test_episode_patterns(
    relative_path,
    series,
    season,
    episode,
):
    candidate = (
        parse_filename_candidate(
            relative_path=relative_path,
            library_content_type="tv",
        )
    )

    assert candidate.kind == "episode"
    assert candidate.series_title == series
    assert candidate.season_number == season
    assert candidate.episode_number == episode


def test_movie_folder_identity():
    candidate = (
        parse_filename_candidate(
            relative_path=(
                "Blade Runner (1982)/"
                "Blade Runner Final Cut "
                "2160p.mkv"
            ),
            library_content_type="movies",
        )
    )

    assert candidate.kind == "movie"
    assert candidate.title == "Blade Runner"
    assert candidate.year == 1982


def test_unrecognized_tv_file_stays_unknown():
    candidate = (
        parse_filename_candidate(
            relative_path="TV/video001.mkv",
            library_content_type="tv",
        )
    )

    assert candidate.kind == "unknown"


def test_identity_conflict_detects_episode_mismatch():
    first = (
        parse_filename_candidate(
            relative_path=(
                "The Expanse/"
                "Season 01/"
                "The Expanse S01E01.mkv"
            ),
            library_content_type="tv",
        )
    )

    second = (
        parse_filename_candidate(
            relative_path=(
                "The Expanse/"
                "Season 01/"
                "The Expanse S01E02.mkv"
            ),
            library_content_type="tv",
        )
    )

    assert identities_conflict(
        first,
        second,
    )


class DummyNfo:
    def __init__(
        self,
        *,
        root_element,
        parsed_data,
    ):
        self.root_element = (
            root_element
        )

        self.parsed_data = (
            parsed_data
        )


def test_jellyfin_series_year_is_not_a_conflict():
    nfo = DummyNfo(
        root_element=(
            "episodedetails"
        ),
        parsed_data={
            "episodedetails": {
                "showtitle":
                    "The Expanse (2015)",

                "season":
                    "1",

                "episode":
                    "3",

                "title":
                    "Remember the Cant",
            }
        },
    )

    nfo_candidate = (
        parse_nfo_candidate(
            nfo
        )
    )

    filename_candidate = (
        parse_filename_candidate(
            relative_path=(
                "The Expanse/"
                "Season 01/"
                "The Expanse "
                "S01E03.mkv"
            ),
            library_content_type=(
                "tv"
            ),
        )
    )

    assert (
        nfo_candidate.series_title
        == "The Expanse"
    )

    assert (
        nfo_candidate.series_year
        == 2015
    )

    assert not identities_conflict(
        nfo_candidate,
        filename_candidate,
    )


def test_episode_title_punctuation_is_not_identity_conflict():
    nfo = DummyNfo(
        root_element=(
            "episodedetails"
        ),
        parsed_data={
            "episodedetails": {
                "showtitle":
                    "Mr. Robot",

                "season":
                    "1",

                "episode":
                    "1",

                "title":
                    "eps1.0_hellofriend.mov",
            }
        },
    )

    nfo_candidate = (
        parse_nfo_candidate(
            nfo
        )
    )

    filename_candidate = (
        parse_filename_candidate(
            relative_path=(
                "Mr Robot/"
                "Season 01/"
                "Mr Robot S01E01 "
                "eps1 0_hellofriend mov.mkv"
            ),
            library_content_type=(
                "tv"
            ),
        )
    )

    assert not identities_conflict(
        nfo_candidate,
        filename_candidate,
    )


def test_slash_and_plus_are_equivalent_for_series_identity():
    nfo = DummyNfo(
        root_element=(
            "episodedetails"
        ),
        parsed_data={
            "episodedetails": {
                "showtitle":
                    "Alpha/Beta",

                "season":
                    "2",

                "episode":
                    "5",

                "title":
                    "Example",
            }
        },
    )

    nfo_candidate = (
        parse_nfo_candidate(
            nfo
        )
    )

    filename_candidate = (
        parse_filename_candidate(
            relative_path=(
                "Alpha+Beta/"
                "Season 02/"
                "Alpha+Beta S02E05.mkv"
            ),
            library_content_type=(
                "tv"
            ),
        )
    )

    assert not identities_conflict(
        nfo_candidate,
        filename_candidate,
    )


@pytest.mark.parametrize(
    (
        "first",
        "second",
    ),
    [
        (
            "Mr. Robot",
            "Mr Robot",
        ),
        (
            "Alpha/Beta",
            "Alpha+Beta",
        ),
        (
            "Law: Order",
            "Law - Order",
        ),
        (
            "Schitt's Creek",
            "Schitts Creek",
        ),
    ],
)
def test_filesystem_title_substitutions_compare_equal(
    first,
    second,
):
    assert (
        identity_text_key(
            first
        )
        == identity_text_key(
            second
        )
    )


def test_numeric_series_title_is_not_treated_as_year_decoration():
    nfo = DummyNfo(
        root_element=(
            "episodedetails"
        ),
        parsed_data={
            "episodedetails": {
                "showtitle":
                    "1923",

                "season":
                    "1",

                "episode":
                    "1",

                "title":
                    "1923",
            }
        },
    )

    candidate = (
        parse_nfo_candidate(
            nfo
        )
    )

    assert (
        candidate.series_title
        == "1923"
    )

    assert (
        candidate.series_year
        is None
    )


@pytest.mark.parametrize(
    (
        "relative_path",
        "expected_title",
        "expected_year",
    ),
    [
        (
            "2067 (2020)/2067 (2020).mkv",
            "2067",
            2020,
        ),
        (
            "1917 (2019)/1917 (2019).mkv",
            "1917",
            2019,
        ),
        (
            "2001 A Space Odyssey (1968)/"
            "2001 A Space Odyssey (1968).mkv",
            "2001 A Space Odyssey",
            1968,
        ),
        (
            "2067.2020.1080p.WEB-DL.mkv",
            "2067",
            2020,
        ),
        (
            "1917.2019.2160p.Remux.mkv",
            "1917",
            2019,
        ),
        (
            "1923.mkv",
            "1923",
            None,
        ),
    ],
)
def test_numeric_movie_titles_do_not_become_years(
    relative_path,
    expected_title,
    expected_year,
):
    candidate = (
        parse_filename_candidate(
            relative_path=relative_path,
            library_content_type="movies",
        )
    )

    assert candidate.kind == "movie"
    assert candidate.title == expected_title
    assert candidate.year == expected_year


def test_numeric_tv_series_title_is_preserved_from_folder():
    candidate = (
        parse_filename_candidate(
            relative_path=(
                "1923/"
                "Season 01/"
                "1923 S01E01.mkv"
            ),
            library_content_type="tv",
        )
    )

    assert candidate.kind == "episode"
    assert candidate.series_title == "1923"
    assert candidate.series_year is None
    assert candidate.season_number == 1
    assert candidate.episode_number == 1


def test_numeric_tv_series_with_real_year_decoration():
    candidate = (
        parse_filename_candidate(
            relative_path=(
                "Doctor Who (2005)/"
                "Season 01/"
                "Doctor Who S01E01.mkv"
            ),
            library_content_type="tv",
        )
    )

    assert candidate.kind == "episode"
    assert candidate.series_title == "Doctor Who"
    assert candidate.series_year == 2005

