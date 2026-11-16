# Projections

A projection builds a separate folder from a library, in the layout a media server expects, without changing the library's own files. Every projection works the same way:

1. **Set it up** on the library's **Projections** page.
   * Choose a destination outside every library, inside a folder listed in `LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS` (comma-separated).
   * Choose how media gets there: hardlinks (no extra space, same volume only, one-time acknowledgement, not for Read Only libraries), copies, or symbolic links.
2. **Check for changes.** This builds a stored plan of every file that would be added, updated, relinked, replaced, removed, or kept, with notes about anything skipped. It reads only.
3. **Apply the reviewed plan.** The background worker (`run_scan_worker`) applies exactly that plan, journaling each file, with progress and Cancel.
4. **History** keeps every run's results and per-file details.

The engine is described in [ALPHA6_PROJECTION_DESIGN.md](ALPHA6_PROJECTION_DESIGN.md).

## Layouts

### Movies (Jellyfin)

```text
The Matrix (1999)/
  The Matrix (1999).mkv     the movie's primary version (hardlink, copy, or symlink)
  The Matrix (1999).nfo     movie NFO
  poster.jpg, fanart.jpg, logo.png, banner.jpg, landscape.jpg   the selected artwork, copied
```

* **NFO:** title, original and sort title, plot, tagline, rating, release date, year, runtime, genres, studios, and IMDb, TMDB, and TVDB IDs as `<uniqueid>`, with the first known one as the default.
* **Name clashes:** two movies that would share a folder name get a stable suffix: an IMDb, TMDB, or TVDB ID, else a short LibraryForge ID (`The Matrix (1999) [imdb-tt0133093]`).
* **Skipped:** movies with no file in the library right now are skipped and reported.

### TV shows (Jellyfin)

```text
Bluey (2018)/
  tvshow.nfo, poster.jpg, fanart.jpg, ...
  Season 01/
    poster.jpg                                   selected season artwork, copied
    Bluey S01E01 - Magic Xylophone.mkv
    Bluey S01E01 - Magic Xylophone.nfo           episodedetails NFO
    Bluey S01E01 - Magic Xylophone-thumb.jpg     selected episode thumbnail, copied
```

* **Episode NFOs** carry the show title, season, episode, air date, plot, runtime, and rating. An episode without a rating of its own carries its show's, for parental controls.
* **Skipped:**
  * multi-episode files (`S01E01-E02`), because they need a representation not built yet
  * episodes with no file present
* **One show at a time:** a plan can be limited to one show, the same way the YouTube layout limits plans to one channel.

### Online video channels as TV shows

See [JELLYFIN_YOUTUBE_SHOWS.md](JELLYFIN_YOUTUBE_SHOWS.md).

## Artwork

Artwork is copied, never linked, from the files LibraryForge selected for each item (the artwork tab of the item editor). A changed source image (different size or time) is copied again on the next sync. Embedded cover art isn't projected for movies and TV, and nothing is downloaded while planning or running.

## Names and paths

* **Safe names:** names work on Windows, Linux, and SMB. Reserved names and characters are replaced, and long titles are shortened.
* **Path length:** a file whose whole path would exceed 250 characters is skipped with a note.
* **Collisions:** two files whose names differ only by letter case count as the same file. The second is skipped with a note.

## Profiles

Phase 2 renders movies and TV for **Jellyfin**. Emby, Kodi, and generic profiles come in phase 3. Until then, a movie or TV projection using another profile is blocked with that explanation.

## API

* `GET`/`POST /api/libraries/<id>/projections/` lists or creates a library's projections.
  * The layout follows the library's content type; mixed libraries pass `layout`: `movies`, `tv`, or `youtube_shows`.
  * Optional fields: `link_mode`, `hardlink_acknowledged`, `output_profile`, and `name`.
* Plans, runs, history, and cancellation use the endpoints described in [JELLYFIN_YOUTUBE_SHOWS.md](JELLYFIN_YOUTUBE_SHOWS.md#api). For movies and TV, `channel` in the plan request limits a plan to one show.
