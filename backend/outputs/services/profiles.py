"""Media-server conventions for projections: artwork names and places.

Every profile uses the same folders, file names, and NFO dialect (Kodi-style
``movie``, ``tvshow``, and ``episodedetails`` NFOs with typed ``<uniqueid>``
values, read by all four). They differ in artwork:

=========  ======================================  ==========================  ==============
Profile    Movie art (in ``Title (Year)/``)        Season art                  Episode thumb
=========  ======================================  ==========================  ==============
Jellyfin   poster, fanart, logo, banner,           ``Season 01/poster.jpg``    ``<file>-thumb``
           landscape
Emby       poster, fanart, clearlogo, banner,      ``Season 01/poster.jpg``    ``<file>-thumb``
           landscape
Kodi       ``<file>-poster``, ``-fanart``,         show folder:                ``<file>-thumb``
           ``-clearlogo``, ``-banner``,            ``season01-poster.jpg``,
           ``-landscape``                          ``season-specials-...``
Generic    poster, fanart                          ``Season 01/poster.jpg``    ``<file>-thumb``
=========  ======================================  ==========================  ==============

Show art goes in the show folder under the same names as movie art, without
a file-name prefix.

Sources, checked November 2026:

* Jellyfin: verified on the maintainer's server.
* Emby: emby.media/support/articles/Movie-Naming.html and TV-Naming.html.
  Images are read from series and season folders, and ``{name}-thumb`` sits
  next to an episode.
* Kodi: its source (xbmc/xbmc). ``ART::AddLocalItemArtwork`` matches
  ``<file>-<type>`` always, and bare ``<type>`` only for items in their own
  folder. ``CVideoInfoScannerArt::GetSeasonThumbs`` reads ``seasonNN-<type>``,
  ``season-specials-<type>``, and ``season-all-<type>`` from the show folder
  only. By default (the artwork level isn't Maximum), Kodi picks up only
  poster and fanart for movies; poster, fanart, and banner for shows and
  seasons; and thumb for episodes.

Emby and Kodi are built to these published conventions and aren't verified
on a live server.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from catalog.models import ArtworkFile

Art = ArtworkFile.ArtworkType


@dataclass(frozen=True)
class Profile:
    target: str
    label: str
    verified: bool
    # Selected artwork type -> its art name. Types not listed aren't projected.
    art: dict[str, str]
    # Kodi: movie art is named after the movie file ("<file>-poster.jpg").
    movie_art_prefix: bool = False
    # Kodi: season art lives in the show folder ("season01-poster.jpg").
    season_art_in_show_folder: bool = False
    notes: tuple[str, ...] = field(default=())

    def movie_art(self, base: str, artwork_type: str) -> str:
        name = self.art[artwork_type]
        return f"{base}-{name}" if self.movie_art_prefix else name

    def season_art(self, show_folder: str, season_folder: str, season_number: int, artwork_type: str) -> tuple[str, str]:
        """(folder, file stem) for a season image."""

        name = self.art[artwork_type]
        if not self.season_art_in_show_folder:
            return season_folder, name
        prefix = "season-specials" if season_number == 0 else f"season{season_number:02d}"
        return show_folder, f"{prefix}-{name}"

    def describe(self) -> dict:
        return {"target": self.target, "label": self.label, "verified": self.verified, "notes": list(self.notes)}


_FULL = {
    Art.PRIMARY: "poster",
    Art.BACKDROP: "fanart",
    Art.LOGO: "logo",
    Art.BANNER: "banner",
    Art.THUMB: "landscape",
}

PROFILES = {
    "jellyfin": Profile("jellyfin", "Jellyfin", True, _FULL),
    "emby": Profile(
        "emby",
        "Emby",
        False,
        {**_FULL, Art.LOGO: "clearlogo"},
        notes=("Built to Emby's published naming conventions; not verified on a live Emby server yet.",),
    ),
    "kodi": Profile(
        "kodi",
        "Kodi",
        False,
        {**_FULL, Art.LOGO: "clearlogo"},
        movie_art_prefix=True,
        season_art_in_show_folder=True,
        notes=(
            "Built to Kodi's conventions; not verified on a live Kodi install yet.",
            "Kodi shows logos and landscape art only when Settings > Media > Videos > Artwork level is Maximum.",
            "Use the Local information only scraper for this source so Kodi reads the NFOs and their ratings.",
        ),
    ),
    "generic": Profile(
        "generic",
        "Generic",
        False,
        {Art.PRIMARY: "poster", Art.BACKDROP: "fanart"},
        notes=("Kodi-style NFOs with poster and fanart only, for players without a dedicated profile.",),
    ),
}


def for_target(target: str) -> Profile:
    return PROFILES.get(target, PROFILES["generic"])
