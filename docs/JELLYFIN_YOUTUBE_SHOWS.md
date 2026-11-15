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

1. **Set up the folder.** Choose a destination outside the library. It must be inside `LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS` when that's configured. In production without it, only staff users can choose a destination.
2. **Check.** This lists what a sync would add, update, relink, replace, or remove, per channel. It reads only the database.
3. **Sync** all channels or one at a time. Changes are applied 25 at a time, with progress and Stop. Only one sync per folder runs at a time.

After the first sync, later syncs pick up new downloads, removed videos, renamed titles (the file is renamed and keeps its episode number), changed descriptions, and changed ratings. For example, changing a channel's rating on the Ratings tab updates its `tvshow.nfo` and every episode NFO on the next sync.

## Safety

- **Manifest.** Every file LibraryForge writes there is recorded (`outputs.ProjectionFile`). A sync replaces or deletes only those files. Anything else in the destination, such as your own files or files another tool wrote, is reported as a conflict and left alone.
- **Changed files.** A recorded file is replaced or deleted only if it's unchanged: the same content for NFOs and images, the same size for video links. A file edited by hand is left in place and reported.
- **Interrupted syncs.** Files left by an interrupted sync are adopted when they're exactly what would be written (the same file for videos, identical content for the rest).
- **Folders.** Folders are only removed when a sync leaves them empty.
- **Confined paths.** Paths can't leave the destination, including through links or junctions inside it. Source files are confined to the library folder and only read.
- **Library mode.** Read Only libraries can be checked but not synced; switch the library to Sidecar Only first.

## In Jellyfin

1. Add the destination folder as a **Shows** library.
2. In its metadata settings, keep the **Nfo** metadata reader enabled. Turn off the TubeArchivist plugin and other online metadata downloaders for this library, so the NFOs and their ratings are what Jellyfin uses.
3. Give your child's account access to this library instead of the TubeArchivist one. With every channel rated, you can also block unrated items for that account.
4. After a sync, run a library scan. If this LibraryForge library is linked to that Jellyfin library, **Refresh in Jellyfin** does it.

## API

- `GET /api/libraries/<id>/youtube-shows/` lists the library's Channels as TV shows projections. `POST` with `{"destination_path": "..."}` creates one. It always uses hardlinks and creates a "Jellyfin" output profile if you have none.
- `GET /api/projections/<id>/shows-plan/?channel=<channel id>` returns the plan: a summary by action, per-channel counts and folders, up to 200 planned changes, and any problem with the library or destination folder.
- `POST /api/projections/<id>/shows-sync/` with `{"cursor": null, "batch": 25, "channel": null}` applies one batch. It returns counts, problems, `next_cursor` (null when finished), `remaining`, and `error` when the sync had to stop.
- The template projection `preview` and `run` endpoints refuse this layout.
