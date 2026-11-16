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

### Movies

The trees below use the Jellyfin profile. Other profiles differ only in artwork; see [Profiles](#profiles).

```text
The Matrix (1999)/
  The Matrix (1999).mkv     the movie's primary version (hardlink, copy, or symlink)
  The Matrix (1999).nfo     movie NFO
  poster.jpg, fanart.jpg, logo.png, banner.jpg, landscape.jpg   the selected artwork, copied
```

* **NFO:** title, original and sort title, plot, tagline, rating, release date, year, runtime, genres, studios, and IMDb, TMDB, and TVDB IDs as `<uniqueid>`, with the first known one as the default (shows and episodes prefer TVDB, then TMDB).
* **Name clashes:** two movies that would share a folder name get a stable suffix: an IMDb, TMDB, or TVDB ID, else a short LibraryForge ID (`The Matrix (1999) [imdb-tt0133093]`).
* **Skipped:** movies with no file in the library right now are skipped and reported.

### TV shows

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

### NFOs and artwork in the library

This layout leaves the files where they are and writes NFOs and artwork into the library's own folders. Set it up on the library's **NFO** page; it's available for movie, TV, and mixed libraries in Sidecar Only or Full Control mode. It has no destination, and a library has at most one. Plans, runs, cancellation, and history work as for folders.

* **Missing NFOs** are created beside each movie and episode (`<file>.nfo`), and as `tvshow.nfo` in each series' folder.
* **Existing NFOs** get only the fields LibraryForge has a different value for, through the same field-level writer as the item editor:
  * Every other tag, comment, attribute, and the file's line endings are kept byte for byte.
  * A value only the NFO has is never erased.
  * The plan stores the exact new text. A run writes it only if the file on disk is still exactly what the plan read.
* **Left alone and reported:** NFOs that don't parse, that changed on disk since the last scan, or that exist but aren't indexed. Rescan first.
* **Artwork:** each selected image is copied into the item's folder under the profile's name:
  * Movies, shows, and seasons: `poster.jpg`, `fanart.jpg`, and so on.
  * Kodi movies: `<file>-poster.jpg`.
  * Kodi seasons: `season01-poster.jpg` in the show folder.
  * Episodes: `<file>-thumb.jpg`.
* **Images already there:**
  * An image already at that name with the same bytes is left alone.
  * A different file there is kept as `<name>.libraryforge-backup-<time>.<ext>`, which neither the media servers nor LibraryForge's scanner treat as artwork.
  * LibraryForge's own earlier copy is replaced without a backup if it's unchanged.
* **Deselected images:** once an image is no longer selected, LibraryForge removes its own copy, but only if the copy is unchanged and removal is safe. The **When an image is no longer selected** setting can keep copies instead.
* **Shared folders:** movies that share a folder get artwork only under Kodi's file-named convention, and seasons without a folder of their own only under Kodi's show-folder convention. Otherwise one image would apply to several items.
* **Read Only** libraries are refused when planning and again when running.
* **Media server settings:** in Jellyfin or Emby, keep the server's own NFO and artwork saving off for the library so it doesn't overwrite these files.

## Artwork

Artwork is copied, never linked, from the files LibraryForge selected for each item (the artwork tab of the item editor). A changed source image (different size or time) is copied again on the next sync. Embedded cover art isn't projected for movies and TV, and nothing is downloaded while planning or running.

## Names and paths

* **Safe names:** names work on Windows, Linux, and SMB. Reserved names and characters are replaced, and long titles are shortened.
* **Path length:** a file whose whole path would exceed 250 characters is skipped with a note.
* **Collisions:** two files whose names differ only by letter case count as the same file. The second is skipped with a note.

## Profiles

A projection's output profile names its media server. Every profile uses the same folders, file names, and NFOs (Kodi-style `movie`, `tvshow`, and `episodedetails`, which all four read). Only artwork differs:

| | Jellyfin | Emby | Kodi | Generic |
| --- | --- | --- | --- | --- |
| Movie art | `poster`, `fanart`, `logo`, `banner`, `landscape` | `poster`, `fanart`, `clearlogo`, `banner`, `landscape` | `<file>-poster`, `-fanart`, `-clearlogo`, `-banner`, `-landscape` | `poster`, `fanart` |
| Show art | as movie art | as movie art | `poster`, `fanart`, `clearlogo`, `banner`, `landscape` | `poster`, `fanart` |
| Season art | `Season 01/poster.jpg` | `Season 01/poster.jpg` | show folder: `season01-poster.jpg`, `season-specials-poster.jpg` | `Season 01/poster.jpg` |
| Episode thumb | `<file>-thumb` | `<file>-thumb` | `<file>-thumb` | `<file>-thumb` |
| Checked against | the maintainer's server | Emby's Movie and TV naming articles | Kodi's scanner source | |

* **Verification:** Emby and Kodi are built to these conventions but not yet verified on a live server. Plans for them say so.
* **Kodi setup:**
  * Use the **Local information only** scraper so Kodi reads the NFOs and their ratings.
  * By default Kodi picks up only poster and fanart for movies, and poster, fanart, and banner for shows. Set **Settings > Media > Videos > Artwork level** to **Maximum** for logos and landscape art.
* **Changing a profile:**
  * You can switch a projection to another of your profiles on its Projections page.
  * Open plans are replaced, and the next plan renames the artwork. Media and NFOs stay put.
* **Online video:** the Channels as TV shows layout is the same for every profile.

The reviewed output for each profile is kept as golden fixtures in `backend/outputs/golden/`: one file list per profile and layout, and the NFOs.

## API

* `GET`/`POST /api/libraries/<id>/projections/` lists or creates a library's projections.
  * The layout follows the library's content type; mixed libraries pass `layout`: `movies`, `tv`, or `youtube_shows`.
  * Optional fields: `link_mode`, `hardlink_acknowledged`, `name`, and either `output_profile` or `target`.
  * `target` (`jellyfin`, `emby`, `kodi`, or `generic`) uses your first profile for that server and creates one if you have none. Jellyfin is the default.
* `POST /api/libraries/<id>/projections/` with `{"layout": "library_nfo", "target": ...}` sets up NFO and artwork output in the library; no destination is needed.
* `PATCH /api/projections/<id>/` with `output_profile`, `destination_path`, `link_mode`, or `stale_policy` replaces the projection's open plans.
* Plans, runs, history, and cancellation use the endpoints described in [JELLYFIN_YOUTUBE_SHOWS.md](JELLYFIN_YOUTUBE_SHOWS.md#api). For movies and TV, `channel` in the plan request limits a plan to one show.
