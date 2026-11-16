# Jellyfin folder: YouTube channels as TV shows

TubeArchivist stores videos as `<channel-id>/<video-id>.mp4` and keeps their metadata in its own database. Jellyfin's TubeArchivist plugin reads that database, so Jellyfin never sees readable file names or NFO files, and YouTube videos reach Jellyfin without content ratings. For a parental-controlled account that means a choice between blocking all of YouTube (unrated items blocked) and letting everything through.

A **Channels as TV shows** projection builds a separate folder in the layout Jellyfin expects, with ratings in every NFO, and never changes TubeArchivist's files. It's on the **Projections** tab of an online video library.

## Layout

```
YouTube Shows/
  Kids Songs/
    tvshow.nfo                                   title, description, rating, YouTube channel ID
    poster.jpg, fanart.jpg                       channel artwork
    Season 2024/
      S2024E051201 - Wheels on the Bus [vid1].mp4        hardlink to the original video
      S2024E051201 - Wheels on the Bus [vid1].nfo        episode NFO
      S2024E051201 - Wheels on the Bus [vid1]-thumb.jpg  thumbnail embedded in the video
```

- **Shows and seasons.** Each channel is a show, and each upload year is a season.
- **Episode numbers.** An episode number is the upload month and day plus a same-day counter: `051201` is 12 May, the first video that day. Once a video has a number it keeps it, so videos downloaded later never renumber existing episodes. The NFO's `<season>`, `<episode>`, and `<aired>` carry the same values.
- **File names.** File names leave out the show name, which keeps paths well under Windows' 260-character limit. Titles are limited to 80 characters and show folders to 60. Characters Windows doesn't allow become `_`. Two channels with the same name get their channel ID added to the folder name.
- **NFO contents.** Episode NFOs include the title, show title, season, episode, air date, description, runtime, rating, channel, a tag for Shorts and live streams, and the YouTube video ID.
- **Ratings.** The episode rating is the video's own rating if it has one, otherwise its channel's. `tvshow.nfo` carries the channel's rating and the earliest upload date.
- **Artwork.**
  - Thumbnails come from the image embedded in each video; videos without one get none.
  - The poster and fanart come from the library's artwork integration: TubeArchivist's channel thumbnail and TV art or banner, or YouTube's channel thumbnail. A show's artwork is fetched once.

## Hardlinks

A hardlink is a second name for the same file. The videos use no extra disk space, and TubeArchivist's folder isn't touched, so TubeArchivist keeps working and never downloads anything again.

- **Same volume.** Hardlinks only work within one volume. Put the destination next to the library folder, for example `\\nas\media-library\YouTube Shows` for `\\nas\media-library\Youtube`. If links can't be made there, the sync stops with that explanation.
- **Deleting.** Deleting a video in TubeArchivist leaves the hardlink as the last name for that data. The next sync removes it, which frees the space.
- **Replaced files.** If TubeArchivist replaces a file, for example by downloading it again, the sync links the new file.

## Syncing

1. **Set up the folder.** Choose a destination outside every library, inside a folder listed in `LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS` (required, development included). Confirm the hardlink policy: a hardlink is the same file as the original under a second name, so nothing should write into videos through the output folder. Hardlinks are refused for Read Only libraries; a projection can use copies instead.
2. **Check for changes.** This builds a stored plan of what would be added, updated, relinked, replaced, removed, or kept, per channel. It reads only, except the first time after an upgrade, when it checks the files written before run history existed (section Safety). Click a count to list those changes.
3. **Apply the reviewed plan.** The background worker (`run_scan_worker`) applies exactly that plan, with progress and Cancel. A plan expires after 30 minutes (`LIBRARYFORGE_PROJECTION_PLAN_MINUTES`) and is refused if the output changed since it was built; build a new one.
4. **History.** Every run is kept with its counts, problems, and a per-file journal.

After the first sync, later syncs pick up new downloads, removed videos, renamed titles (the file is renamed and keeps its episode number), changed descriptions, and changed ratings. For example, changing a channel's rating on the Ratings tab updates its `tvshow.nfo` and every episode NFO on the next sync.

**Deleted videos.** By default, files whose video is gone are removed (so the hardlink stops using space), but only files LibraryForge created that are unchanged. They're kept instead, with a note, while a scan is running, when the library's last scan didn't finish, or when the library folder can't be reached. "Keep them" is available per projection.

## Safety

- **Manifest.** Every file LibraryForge writes there is recorded (`outputs.ProjectionFile`). A sync replaces or deletes only those files. Anything else in the destination, such as your own files or files another tool wrote, is reported as a conflict and left alone.
- **Changed files.** A recorded file is replaced or deleted only if it's unchanged: the same content for NFOs and images, the same size for video links. A file edited by hand is left in place and reported.
- **Run journal.** Each change is recorded as started before the disk is touched, then as done, skipped, or failed. After an interrupted run, a file is adopted only where the journal shows that run was creating it and it's exactly what would be written; a matching file alone is never adopted.
- **Before each change.** The run rechecks the output's recorded state and the source file's size; anything that changed since the plan was built is skipped and reported.
- **Files from before run history.** Files written by alpha.5 are verified once, on the first plan: links must still be the same file as their source and NFOs and images must have the recorded hash. Verified files are kept, missing ones are recreated, and anything else is left alone.
- **Output isn't a library.** A projection's folder can't overlap any library, and a library can't be created over a projection's folder.
- **Folders.** Folders are only removed when a sync leaves them empty.
- **Confined paths.** Paths can't leave the destination, including through links or junctions inside it. Source files are confined to the library folder and only read.
- **Library mode.** Read Only libraries can be checked but not synced; switch the library to Sidecar Only first.

## In Jellyfin

1. Add the destination folder as a **Shows** library.
2. In its metadata settings, keep the **Nfo** metadata reader enabled. Turn off the TubeArchivist plugin and other online metadata downloaders for this library, so the NFOs and their ratings are what Jellyfin uses.
3. Give your child's account access to this library instead of the TubeArchivist one. With every channel rated, you can also block unrated items for that account.
4. After a sync, run a library scan. If this LibraryForge library is linked to that Jellyfin library, **Refresh in Jellyfin** does it.

## API

- `GET /api/libraries/<id>/youtube-shows/` lists the library's Channels as TV shows projections. `POST` with `{"destination_path": "...", "hardlink_acknowledged": true}` creates one, with a "Jellyfin" output profile if you have none.
- `PATCH /api/projections/<id>/` changes `stale_policy` (`remove_owned` or `keep`), `hardlink_acknowledged`, or `enabled`. It never touches disk.
- `POST /api/projections/<id>/plans/` (optional `{"channel": "<id>"}`) builds a plan. It returns its status, digest, counts, findings, overview (channels, folders), and the first 100 changes. `GET /api/projection-plans/<id>/actions/?page=&action=` pages through all of them.
- `POST /api/projection-plans/<id>/runs/` with `{"digest", "idempotency_key"}` queues a run (202). A repeated key returns the same run. A stale, expired, or blocked plan is refused (409 or 422).
- `GET /api/projection-runs/<id>/`, `GET /api/projection-runs/<id>/actions/?problems=1`, and `POST /api/projection-runs/<id>/cancel/` show progress and the journal, and cancel.
- `GET /api/projections/<id>/runs/` lists recent runs and the number of managed files.
