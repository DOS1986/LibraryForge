# LibraryForge

**Your media. Your metadata. Your structure.**

LibraryForge is a self-hosted media metadata and library management platform.

Website: coming soon

## Goals

LibraryForge is designed to manage and organize media from sources including:

- Movies
- TV shows
- TubeArchivist
- yt-dlp archives
- OBS recordings
- Home videos
- Lectures and courses
- Podcast video
- Music videos
- Generic video archives

LibraryForge can:

- Inspect embedded metadata
- Edit metadata
- Bulk edit metadata
- Rename and reorganize files
- Generate NFO files
- Manage artwork
- Create Jellyfin-compatible libraries
- Create Emby-compatible libraries
- Create Kodi-compatible libraries
- Create projected libraries using hardlinks or symlinks
- Preserve read-only source archives
- Track changes and support undo

## Stack

### Backend

- Python
- Django
- Django REST Framework
- PostgreSQL

### Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- shadcn/ui
- TanStack Query

### Media tooling

- FFmpeg
- ffprobe
- MKVToolNix
- ExifTool

## Running LibraryForge

LibraryForge runs as two backend processes plus the frontend:

- the **web server** (`uv run python manage.py runserver`, in `backend/`)
- the **scan worker** (`uv run python manage.py run_scan_worker`, in `backend/`), which runs library scans

Scans requested in the UI wait in a queue until a scan worker picks them up, so without a worker they never start. The scan panel and Jobs page say when no worker is running.

On Windows, `scripts/dev.ps1` starts the web server, scan worker, and frontend together. `scripts/dev.sh` and `scripts/dev.command` do the same on Linux and macOS.

### Scanning several libraries at once

Each worker scans one library at a time. To scan more than one library in parallel, run several workers with `--workers N` (1 to 8):

```
uv run python manage.py run_scan_worker --workers 2
```

That starts a small supervisor plus N worker processes. Each worker claims a different queued scan, and a library never has more than one active scan. The supervisor restarts a worker that crashes, waits for every worker to finish its current scan on a restart request, and stops them all on Ctrl+C. To set the default, including for `scripts/dev.*`, add `LIBRARYFORGE_SCAN_WORKERS=2` to `.env`.

Scanning is mostly network and disk reads plus `ffprobe`, so libraries on the same NAS share its bandwidth. Two or three workers is usually the useful limit there.

## Website

coming soon
