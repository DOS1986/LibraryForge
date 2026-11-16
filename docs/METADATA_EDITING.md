# Editing metadata and NFO files

LibraryForge's catalog is where metadata is edited. Metadata gets there from embedded tags, NFOs, TubeArchivist, providers, or by hand. NFO files are kept in step with it, so media servers such as Jellyfin read the same values.

## Editing items

- **Movies, series, seasons, and episodes:** open an item from the library's Media page. The **Metadata** tab edits its fields.
- **Online videos and channels:** on the Media page of an online video library, open a video or channel and choose **Edit**. You can change the title, description, rating, upload date, and tags (for channels: title, sort title, description, and rating).

Saved fields are recorded as manual edits. Each is locked against later scans and gets a history entry, so a rescan never overwrites what you typed. The item's **History** tab lists every change.

## Writing to NFO files

An item's **NFO** tab (movies, series, and episodes) puts LibraryForge's fields beside its NFO, with a status for each:

| Status | Meaning |
| --- | --- |
| Matches | The NFO has the same value. |
| Differs | The NFO has a different value. Tick it to write LibraryForge's value. |
| Not in NFO | LibraryForge has a value the NFO lacks. Tick it to add it. |
| Only in NFO (kept) | The NFO has a value LibraryForge doesn't. It's never erased from here. |
| Empty | Neither has a value. |

The fields are title, original and sort title, plot, tagline, rating, release date and year, genres, and studios for movies. Series have the same set, with the first-aired year in place of the release date and year. Episodes have title, plot, season, episode, air date, and rating.

- **Existing NFOs.** Only the ticked fields change. Every other tag (cast, artwork links, IDs, custom tags), the comments, the formatting, and the line endings are kept byte for byte. Only top-level fields are touched, so an actor's `<name>` or a set's `<overview>` is never changed. Duplicate copies of a field are reduced to one, because Jellyfin reads the last copy.
- **Missing NFOs.** **Create NFO** writes one with everything LibraryForge has, in the names Jellyfin reads: `<video file name>.nfo` beside a movie or episode, and `tvshow.nfo` in a series' folder.
- **Whole libraries.** The NFO page of a movie, TV, or mixed library has **NFOs and artwork in this library**. It plans and applies, in the background, every missing NFO, every changed field in existing NFOs, and the selected artwork under a media server's names. See [PROJECTIONS.md](PROJECTIONS.md#nfos-and-artwork-in-the-library).

### Safety

- **Library mode.** Read Only libraries can be compared but not written; switch them to Sidecar Only first.
- **Changed files.** An NFO that changed on disk since the last scan isn't overwritten; rescan first. A file at the planned path that LibraryForge hasn't indexed is never replaced.
- **Checked writes.** Every edited NFO is parsed again and must read back the written values before it's saved. Files are written atomically and only inside the library folder.

`GET /api/catalog-editor/<movies|series|episodes>/<id>/nfo/` returns the comparison. `POST` with `{"fields": [...]}` writes those fields. Omit `fields` to write every difference, or to create a missing NFO. `GET`/`POST /api/libraries/<id>/nfo-create/?kind=movie|series` previews or creates missing NFOs in batches. `GET`/`PATCH /api/catalog-editor/online-videos/<id>/` and `/api/catalog-editor/channels/<id>/` edit online videos and channels.

## YouTube videos

YouTube NFOs live only in the Jellyfin "Channels as TV shows" folder (see [JELLYFIN_YOUTUBE_SHOWS.md](JELLYFIN_YOUTUBE_SHOWS.md)). TubeArchivist's folder isn't given NFO files. Edit a video or channel in LibraryForge; the folder's next sync rewrites its episode NFOs and `tvshow.nfo` with the new values, renaming the file if the title changed.

Don't edit those NFOs by hand: the sync treats a hand-edited file as changed outside LibraryForge and stops updating it.

### Keeping embedded tags out of Jellyfin

The video files still carry their embedded tags (title, description, cover art). To make Jellyfin use the NFOs and local images instead:

1. Make sure every video has an NFO and thumbnail. The Shows folder writes both for every video.
2. In the Jellyfin library's settings, turn off the option to use embedded titles (Jellyfin's `EnableEmbeddedTitles` library option). Embedded titles replace the name whenever that option is on.
3. Leave the Nfo metadata reader enabled; Jellyfin documents that local metadata takes priority over online providers. An embedded description only fills an empty overview, so an NFO with a plot keeps it out.
4. Local images (`poster.jpg`, `<name>-thumb.jpg`) take precedence over other image sources, including embedded cover art. You can also disable the "Embedded Image Extractor" image fetcher for the library.

These Jellyfin details come from its documentation and server source. Labels can differ between Jellyfin versions.
