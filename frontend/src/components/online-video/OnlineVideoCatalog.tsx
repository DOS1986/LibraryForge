import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react"

import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ExternalLink,
} from "lucide-react"

import {
  Badge,
} from "@/components/ui/badge"

import {
  Button,
} from "@/components/ui/button"

import {
  Dialog,
  DialogTitle,
} from "@/components/ui/dialog"

import {
  Input,
} from "@/components/ui/input"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"

import {
  ScrollableDialogBody,
  ScrollableDialogContent,
  ScrollableDialogHeader,
} from "@/components/dialogs/ScrollableDialog"

import {
  MediaDetailDialog,
} from "@/components/media/MediaDetailDialog"

import {
  TablePagination,
} from "@/components/tables/TablePagination"

import {
  formatBytes,
  formatDuration,
} from "@/lib/format"

import {
  getOnlineVideoChannels,
  getOnlineVideoPlaylists,
  getOnlineVideos,
  type OnlineVideoCatalogItem,
  type OnlineVideoChannel,
  type OnlineVideoPlaylist,
} from "@/lib/online-video-api"

import type {
  Library,
  PageSize,
} from "@/types"


type OnlineVideoView =
  | "channels"
  | "playlists"
  | "videos"


type ChannelSort =
  | "title"
  | "video_count"
  | "runtime_seconds"
  | "storage_bytes"
  | "last_upload_date"


type PlaylistSort =
  | "title"
  | "channel__title"
  | "video_count"
  | "runtime_seconds"
  | "storage_bytes"


type VideoSort =
  | "media_item__title"
  | "channel__title"
  | "upload_date"
  | "video_kind"
  | "runtime_seconds"
  | "storage_bytes"
  | "playlist_count"


function formatDate(
  value: string | null,
) {
  if (!value) {
    return "—"
  }

  return new Date(
    `${value}T00:00:00`,
  ).toLocaleDateString()
}


function providerLabel(
  provider: string,
) {
  if (!provider) {
    return "Unknown"
  }

  if (provider === "youtube") {
    return "YouTube"
  }

  return provider
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(
      /\b\w/g,
      value => value.toUpperCase(),
    )
}


function kindLabel(
  kind: string,
) {
  switch (kind) {
    case "short":
      return "Short"
    case "stream":
      return "Stream"
    case "video":
      return "Video"
    default:
      return "Unknown"
  }
}


function SortButton<T extends string>({
  label,
  field,
  sortField,
  descending,
  onSort,
}: {
  label: string
  field: T
  sortField: T
  descending: boolean
  onSort: (field: T) => void
}) {
  const active =
    field === sortField

  return (
    <button
      type="button"
      onClick={
        () => onSort(field)
      }
      className="inline-flex items-center gap-1 font-medium"
    >
      {label}

      {
        !active
          ? (
            <ArrowUpDown className="h-3.5 w-3.5" />
          )
          : descending
            ? (
              <ArrowDown className="h-3.5 w-3.5" />
            )
            : (
              <ArrowUp className="h-3.5 w-3.5" />
            )
      }
    </button>
  )
}


function EmptyRow({
  colSpan,
  text,
}: {
  colSpan: number
  text: string
}) {
  return (
    <tr>
      <td
        colSpan={colSpan}
        className="p-8 text-center text-muted-foreground"
      >
        {text}
      </td>
    </tr>
  )
}


function ErrorPanel({
  error,
}: {
  error: string | null
}) {
  if (!error) {
    return null
  }

  return (
    <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
      {error}
    </div>
  )
}


function ChannelCatalog({
  library,
  refreshKey,
  onOpenChannel,
}: {
  library: Library
  refreshKey: string
  onOpenChannel: (channel: OnlineVideoChannel) => void
}) {
  const [channels, setChannels] = useState<OnlineVideoChannel[]>([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<PageSize>(20)
  const [totalPages, setTotalPages] = useState(1)
  const [search, setSearch] = useState("")
  const [sortField, setSortField] = useState<ChannelSort>("title")
  const [descending, setDescending] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ordering =
    descending
      ? `-${sortField}`
      : sortField

  const load =
    useCallback(
      async () => {
        setLoading(true)
        setError(null)

        try {
          const result = await getOnlineVideoChannels({
            libraryId: library.id,
            search,
            ordering,
            page,
            pageSize,
          })

          setChannels(result.results)
          setCount(result.count)
          setTotalPages(result.total_pages)
        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load channels.",
          )
        } finally {
          setLoading(false)
        }
      },
      [
        library.id,
        search,
        ordering,
        page,
        pageSize,
        refreshKey,
      ],
    )

  useEffect(
    () => {
      void load()
    },
    [load],
  )

  function handleSort(field: ChannelSort) {
    setPage(1)

    if (field === sortField) {
      setDescending(!descending)
      return
    }

    setSortField(field)
    setDescending(false)
  }

  return (
    <div className="space-y-4">
      <Input
        value={search}
        onChange={
          event => {
            setSearch(event.target.value)
            setPage(1)
          }
        }
        placeholder="Search channels..."
      />

      <ErrorPanel error={error} />

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[900px] text-sm">
          <thead>
            <tr className="border-b bg-muted/40 text-left">
              <th className="p-3">
                <SortButton
                  label="Channel"
                  field="title"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">Provider</th>
              <th className="p-3">
                <SortButton
                  label="Videos"
                  field="video_count"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">
                <SortButton
                  label="Runtime"
                  field="runtime_seconds"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">
                <SortButton
                  label="Storage"
                  field="storage_bytes"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">
                <SortButton
                  label="Latest Upload"
                  field="last_upload_date"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
            </tr>
          </thead>

          <tbody>
            {loading && channels.length === 0 && (
              <EmptyRow colSpan={6} text="Loading channels..." />
            )}

            {!loading && channels.length === 0 && (
              <EmptyRow colSpan={6} text="No channels found." />
            )}

            {channels.map(channel => (
              <tr
                key={channel.id}
                onClick={() => onOpenChannel(channel)}
                className="cursor-pointer border-b hover:bg-muted/50"
              >
                <td className="p-3">
                  <div className="font-medium">
                    {channel.title || channel.source_id}
                  </div>
                  <div className="max-w-[360px] truncate text-xs text-muted-foreground">
                    {channel.handle || channel.source_id}
                  </div>
                </td>
                <td className="p-3">
                  <Badge variant="outline">
                    {providerLabel(channel.provider)}
                  </Badge>
                </td>
                <td className="p-3 tabular-nums">
                  {channel.video_count.toLocaleString()}
                </td>
                <td className="p-3 tabular-nums">
                  {formatDuration(channel.runtime_seconds)}
                </td>
                <td className="p-3 tabular-nums">
                  {formatBytes(channel.storage_bytes)}
                </td>
                <td className="p-3">
                  {formatDate(channel.last_upload_date)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <TablePagination
        page={page}
        pageSize={pageSize}
        totalPages={totalPages}
        count={count}
        onPageChange={setPage}
        onPageSizeChange={
          value => {
            setPageSize(value)
            setPage(1)
          }
        }
      />
    </div>
  )
}


function PlaylistCatalog({
  library,
  refreshKey,
  onOpenPlaylist,
}: {
  library: Library
  refreshKey: string
  onOpenPlaylist: (playlist: OnlineVideoPlaylist) => void
}) {
  const [playlists, setPlaylists] = useState<OnlineVideoPlaylist[]>([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<PageSize>(20)
  const [totalPages, setTotalPages] = useState(1)
  const [search, setSearch] = useState("")
  const [sortField, setSortField] = useState<PlaylistSort>("title")
  const [descending, setDescending] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ordering =
    descending
      ? `-${sortField}`
      : sortField

  const load =
    useCallback(
      async () => {
        setLoading(true)
        setError(null)

        try {
          const result = await getOnlineVideoPlaylists({
            libraryId: library.id,
            search,
            ordering,
            page,
            pageSize,
          })

          setPlaylists(result.results)
          setCount(result.count)
          setTotalPages(result.total_pages)
        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load playlists.",
          )
        } finally {
          setLoading(false)
        }
      },
      [
        library.id,
        search,
        ordering,
        page,
        pageSize,
        refreshKey,
      ],
    )

  useEffect(
    () => {
      void load()
    },
    [load],
  )

  function handleSort(field: PlaylistSort) {
    setPage(1)

    if (field === sortField) {
      setDescending(!descending)
      return
    }

    setSortField(field)
    setDescending(false)
  }

  return (
    <div className="space-y-4">
      <Input
        value={search}
        onChange={
          event => {
            setSearch(event.target.value)
            setPage(1)
          }
        }
        placeholder="Search playlists..."
      />

      <ErrorPanel error={error} />

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[940px] text-sm">
          <thead>
            <tr className="border-b bg-muted/40 text-left">
              <th className="p-3">
                <SortButton
                  label="Playlist"
                  field="title"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">
                <SortButton
                  label="Channel"
                  field="channel__title"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">Type</th>
              <th className="p-3">
                <SortButton
                  label="Videos"
                  field="video_count"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">
                <SortButton
                  label="Runtime"
                  field="runtime_seconds"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">
                <SortButton
                  label="Storage"
                  field="storage_bytes"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
            </tr>
          </thead>

          <tbody>
            {loading && playlists.length === 0 && (
              <EmptyRow colSpan={6} text="Loading playlists..." />
            )}

            {!loading && playlists.length === 0 && (
              <EmptyRow colSpan={6} text="No playlists found." />
            )}

            {playlists.map(playlist => (
              <tr
                key={playlist.id}
                onClick={() => onOpenPlaylist(playlist)}
                className="cursor-pointer border-b hover:bg-muted/50"
              >
                <td className="p-3">
                  <div className="font-medium">
                    {playlist.title || playlist.source_id}
                  </div>
                  <div className="max-w-[340px] truncate text-xs text-muted-foreground">
                    {playlist.source_id}
                  </div>
                </td>
                <td className="p-3">
                  {playlist.channel_title || "—"}
                </td>
                <td className="p-3">
                  <Badge variant="outline">
                    {playlist.playlist_kind}
                  </Badge>
                </td>
                <td className="p-3 tabular-nums">
                  {playlist.video_count.toLocaleString()}
                </td>
                <td className="p-3 tabular-nums">
                  {formatDuration(playlist.runtime_seconds)}
                </td>
                <td className="p-3 tabular-nums">
                  {formatBytes(playlist.storage_bytes)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <TablePagination
        page={page}
        pageSize={pageSize}
        totalPages={totalPages}
        count={count}
        onPageChange={setPage}
        onPageSizeChange={
          value => {
            setPageSize(value)
            setPage(1)
          }
        }
      />
    </div>
  )
}


function VideoCatalog({
  library,
  refreshKey,
  onOpenVideo,
}: {
  library: Library
  refreshKey: string
  onOpenVideo: (video: OnlineVideoCatalogItem) => void
}) {
  const [videos, setVideos] = useState<OnlineVideoCatalogItem[]>([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<PageSize>(20)
  const [totalPages, setTotalPages] = useState(1)
  const [search, setSearch] = useState("")
  const [sortField, setSortField] = useState<VideoSort>("upload_date")
  const [descending, setDescending] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ordering =
    descending
      ? `-${sortField}`
      : sortField

  const load =
    useCallback(
      async () => {
        setLoading(true)
        setError(null)

        try {
          const result = await getOnlineVideos({
            libraryId: library.id,
            search,
            ordering,
            page,
            pageSize,
          })

          setVideos(result.results)
          setCount(result.count)
          setTotalPages(result.total_pages)
        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load videos.",
          )
        } finally {
          setLoading(false)
        }
      },
      [
        library.id,
        search,
        ordering,
        page,
        pageSize,
        refreshKey,
      ],
    )

  useEffect(
    () => {
      void load()
    },
    [load],
  )

  function handleSort(field: VideoSort) {
    setPage(1)

    if (field === sortField) {
      setDescending(!descending)
      return
    }

    setSortField(field)
    setDescending(field === "upload_date")
  }

  return (
    <div className="space-y-4">
      <Input
        value={search}
        onChange={
          event => {
            setSearch(event.target.value)
            setPage(1)
          }
        }
        placeholder="Search videos, channels, IDs, and file paths..."
      />

      <ErrorPanel error={error} />

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[1120px] text-sm">
          <thead>
            <tr className="border-b bg-muted/40 text-left">
              <th className="p-3">
                <SortButton
                  label="Title"
                  field="media_item__title"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">
                <SortButton
                  label="Channel"
                  field="channel__title"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">
                <SortButton
                  label="Published"
                  field="upload_date"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">
                <SortButton
                  label="Type"
                  field="video_kind"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">
                <SortButton
                  label="Runtime"
                  field="runtime_seconds"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">
                <SortButton
                  label="Playlists"
                  field="playlist_count"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
              <th className="p-3">Versions</th>
              <th className="p-3">
                <SortButton
                  label="Storage"
                  field="storage_bytes"
                  sortField={sortField}
                  descending={descending}
                  onSort={handleSort}
                />
              </th>
            </tr>
          </thead>

          <tbody>
            {loading && videos.length === 0 && (
              <EmptyRow colSpan={8} text="Loading videos..." />
            )}

            {!loading && videos.length === 0 && (
              <EmptyRow colSpan={8} text="No videos found." />
            )}

            {videos.map(video => (
              <tr
                key={video.id}
                onClick={() => onOpenVideo(video)}
                className="cursor-pointer border-b hover:bg-muted/50"
              >
                <td className="p-3">
                  <div className="max-w-[360px] truncate font-medium" title={video.title}>
                    {video.title || video.source_id}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {video.source_id}
                  </div>
                </td>
                <td className="p-3">
                  <div className="max-w-[260px] truncate" title={video.channel_title ?? undefined}>
                    {video.channel_title || "—"}
                  </div>
                </td>
                <td className="p-3">
                  {formatDate(video.upload_date || video.release_date)}
                </td>
                <td className="p-3">
                  <Badge variant="outline">
                    {kindLabel(video.video_kind)}
                  </Badge>
                </td>
                <td className="p-3 tabular-nums">
                  {formatDuration(video.runtime_seconds)}
                </td>
                <td className="p-3 tabular-nums">
                  {video.playlist_count.toLocaleString()}
                </td>
                <td className="p-3 tabular-nums">
                  {video.version_count.toLocaleString()}
                </td>
                <td className="p-3 tabular-nums">
                  {formatBytes(video.storage_bytes)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <TablePagination
        page={page}
        pageSize={pageSize}
        totalPages={totalPages}
        count={count}
        onPageChange={setPage}
        onPageSizeChange={
          value => {
            setPageSize(value)
            setPage(1)
          }
        }
      />
    </div>
  )
}


function RelatedVideosTable({
  libraryId,
  channelId,
  playlistId,
  onOpenVideo,
}: {
  libraryId: string
  channelId?: string
  playlistId?: string
  onOpenVideo: (video: OnlineVideoCatalogItem) => void
}) {
  const [videos, setVideos] = useState<OnlineVideoCatalogItem[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<PageSize>(10)
  const [count, setCount] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [search, setSearch] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load =
    useCallback(
      async () => {
        setLoading(true)
        setError(null)

        try {
          const result = await getOnlineVideos({
            libraryId,
            channelId,
            playlistId,
            search,
            ordering: playlistId
              ? "playlist_memberships__position"
              : "-upload_date",
            page,
            pageSize,
          })

          setVideos(result.results)
          setCount(result.count)
          setTotalPages(result.total_pages)
        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load videos.",
          )
        } finally {
          setLoading(false)
        }
      },
      [
        libraryId,
        channelId,
        playlistId,
        search,
        page,
        pageSize,
      ],
    )

  useEffect(
    () => {
      void load()
    },
    [load],
  )

  return (
    <div className="space-y-4">
      <Input
        value={search}
        onChange={
          event => {
            setSearch(event.target.value)
            setPage(1)
          }
        }
        placeholder="Search videos..."
      />

      <ErrorPanel error={error} />

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b bg-muted/40 text-left">
              {playlistId && <th className="p-3">#</th>}
              <th className="p-3">Title</th>
              <th className="p-3">Published</th>
              <th className="p-3">Runtime</th>
              <th className="p-3">Storage</th>
            </tr>
          </thead>
          <tbody>
            {loading && videos.length === 0 && (
              <EmptyRow colSpan={playlistId ? 5 : 4} text="Loading videos..." />
            )}
            {!loading && videos.length === 0 && (
              <EmptyRow colSpan={playlistId ? 5 : 4} text="No videos found." />
            )}
            {videos.map(video => {
              const membership = playlistId
                ? video.playlists.find(
                  item => item.playlist.id === playlistId,
                )
                : null

              return (
                <tr
                  key={video.id}
                  onClick={() => onOpenVideo(video)}
                  className="cursor-pointer border-b hover:bg-muted/50"
                >
                  {playlistId && (
                    <td className="p-3 tabular-nums text-muted-foreground">
                      {membership?.position ?? "—"}
                    </td>
                  )}
                  <td className="p-3">
                    <div className="font-medium">
                      {video.title}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {video.channel_title || video.source_id}
                    </div>
                  </td>
                  <td className="p-3">
                    {formatDate(video.upload_date || video.release_date)}
                  </td>
                  <td className="p-3 tabular-nums">
                    {formatDuration(video.runtime_seconds)}
                  </td>
                  <td className="p-3 tabular-nums">
                    {formatBytes(video.storage_bytes)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <TablePagination
        page={page}
        pageSize={pageSize}
        totalPages={totalPages}
        count={count}
        onPageChange={setPage}
        onPageSizeChange={
          value => {
            setPageSize(value)
            setPage(1)
          }
        }
      />
    </div>
  )
}


function Stat({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <div className="text-xs text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 font-medium tabular-nums">
        {value}
      </div>
    </div>
  )
}


function ChannelDialog({
  channel,
  onClose,
  onOpenVideo,
}: {
  channel: OnlineVideoChannel | null
  onClose: () => void
  onOpenVideo: (video: OnlineVideoCatalogItem) => void
}) {
  return (
    <Dialog
      open={channel !== null}
      onOpenChange={open => {
        if (!open) {
          onClose()
        }
      }}
    >
      <ScrollableDialogContent>
        {channel && (
          <>
            <ScrollableDialogHeader>
              <DialogTitle>
                {channel.title || channel.source_id}
              </DialogTitle>
            </ScrollableDialogHeader>

            <ScrollableDialogBody>
              <div className="space-y-5">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">
                    {providerLabel(channel.provider)}
                  </Badge>
                  {channel.handle && (
                    <Badge variant="secondary">
                      {channel.handle}
                    </Badge>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {channel.source_id}
                  </span>
                </div>

                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Stat label="Videos" value={channel.video_count.toLocaleString()} />
                  <Stat label="Runtime" value={formatDuration(channel.runtime_seconds)} />
                  <Stat label="Storage" value={formatBytes(channel.storage_bytes)} />
                  <Stat label="Latest Upload" value={formatDate(channel.last_upload_date)} />
                </div>

                {channel.description && (
                  <div>
                    <div className="mb-1 text-sm font-medium">
                      Description
                    </div>
                    <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                      {channel.description}
                    </p>
                  </div>
                )}

                {channel.source_url && (
                  <a
                    href={channel.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                  >
                    Open source channel
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}

                <div>
                  <div className="mb-3 text-sm font-medium">
                    Videos
                  </div>
                  <RelatedVideosTable
                    libraryId={channel.library}
                    channelId={channel.id}
                    onOpenVideo={onOpenVideo}
                  />
                </div>
              </div>
            </ScrollableDialogBody>
          </>
        )}
      </ScrollableDialogContent>
    </Dialog>
  )
}


function PlaylistDialog({
  playlist,
  onClose,
  onOpenVideo,
}: {
  playlist: OnlineVideoPlaylist | null
  onClose: () => void
  onOpenVideo: (video: OnlineVideoCatalogItem) => void
}) {
  return (
    <Dialog
      open={playlist !== null}
      onOpenChange={open => {
        if (!open) {
          onClose()
        }
      }}
    >
      <ScrollableDialogContent>
        {playlist && (
          <>
            <ScrollableDialogHeader>
              <DialogTitle>
                {playlist.title || playlist.source_id}
              </DialogTitle>
            </ScrollableDialogHeader>

            <ScrollableDialogBody>
              <div className="space-y-5">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">
                    {providerLabel(playlist.provider)}
                  </Badge>
                  <Badge variant="secondary">
                    {playlist.playlist_kind}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {playlist.source_id}
                  </span>
                </div>

                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Stat label="Videos" value={playlist.video_count.toLocaleString()} />
                  <Stat label="Runtime" value={formatDuration(playlist.runtime_seconds)} />
                  <Stat label="Storage" value={formatBytes(playlist.storage_bytes)} />
                  <Stat label="Channel" value={playlist.channel_title || "—"} />
                </div>

                {playlist.description && (
                  <div>
                    <div className="mb-1 text-sm font-medium">
                      Description
                    </div>
                    <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                      {playlist.description}
                    </p>
                  </div>
                )}

                {playlist.source_url && (
                  <a
                    href={playlist.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                  >
                    Open source playlist
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}

                <div>
                  <div className="mb-3 text-sm font-medium">
                    Playlist Videos
                  </div>
                  <RelatedVideosTable
                    libraryId={playlist.library}
                    playlistId={playlist.id}
                    onOpenVideo={onOpenVideo}
                  />
                </div>
              </div>
            </ScrollableDialogBody>
          </>
        )}
      </ScrollableDialogContent>
    </Dialog>
  )
}


function VideoDialog({
  video,
  onClose,
  onOpenMediaDetails,
}: {
  video: OnlineVideoCatalogItem | null
  onClose: () => void
  onOpenMediaDetails: (mediaItemId: string) => void
}) {
  return (
    <Dialog
      open={video !== null}
      onOpenChange={open => {
        if (!open) {
          onClose()
        }
      }}
    >
      <ScrollableDialogContent>
        {video && (
          <>
            <ScrollableDialogHeader>
              <DialogTitle>
                {video.title || video.source_id}
              </DialogTitle>
            </ScrollableDialogHeader>

            <ScrollableDialogBody>
              <div className="space-y-6">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">
                    {providerLabel(video.provider)}
                  </Badge>
                  <Badge variant="secondary">
                    {kindLabel(video.video_kind)}
                  </Badge>
                  {video.locked && (
                    <Badge variant="outline">
                      Locked
                    </Badge>
                  )}
                </div>

                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Stat label="Channel" value={video.channel_title || "—"} />
                  <Stat label="Published" value={formatDate(video.upload_date || video.release_date)} />
                  <Stat label="Runtime" value={formatDuration(video.runtime_seconds)} />
                  <Stat label="Storage" value={formatBytes(video.storage_bytes)} />
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <div className="text-xs text-muted-foreground">Video ID</div>
                    <div className="mt-1 break-all font-mono text-sm">
                      {video.source_id}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">Semantic Key</div>
                    <div className="mt-1 break-all font-mono text-sm">
                      {video.semantic_key}
                    </div>
                  </div>
                </div>

                {video.description && (
                  <div>
                    <div className="mb-1 text-sm font-medium">
                      Description
                    </div>
                    <p className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/20 p-3 text-sm text-muted-foreground">
                      {video.description}
                    </p>
                  </div>
                )}

                {(video.tags.length > 0 || video.categories.length > 0) && (
                  <div className="space-y-3">
                    {video.categories.length > 0 && (
                      <div>
                        <div className="mb-2 text-sm font-medium">Categories</div>
                        <div className="flex flex-wrap gap-2">
                          {video.categories.map(category => (
                            <Badge key={category} variant="secondary">
                              {category}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}

                    {video.tags.length > 0 && (
                      <div>
                        <div className="mb-2 text-sm font-medium">Tags</div>
                        <div className="flex flex-wrap gap-2">
                          {video.tags.map(tag => (
                            <Badge key={tag} variant="outline">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                <div>
                  <div className="mb-2 text-sm font-medium">
                    Playlists ({video.playlist_count})
                  </div>
                  {video.playlists.length === 0 ? (
                    <div className="text-sm text-muted-foreground">
                      This video is not associated with an indexed playlist.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {video.playlists.map(membership => (
                        <div
                          key={membership.id}
                          className="flex items-center justify-between gap-3 rounded-md border p-3 text-sm"
                        >
                          <div className="min-w-0">
                            <div className="truncate font-medium">
                              {membership.playlist.title}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {membership.playlist.channel_title || membership.playlist.source_id}
                            </div>
                          </div>
                          <div className="shrink-0 tabular-nums text-muted-foreground">
                            {membership.position === null
                              ? "—"
                              : `#${membership.position}`}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <div className="mb-2 text-sm font-medium">
                    Physical Versions ({video.version_count})
                  </div>
                  <div className="overflow-x-auto rounded-md border">
                    <table className="w-full min-w-[760px] text-sm">
                      <thead>
                        <tr className="border-b bg-muted/40 text-left">
                          <th className="p-3">File</th>
                          <th className="p-3">Video</th>
                          <th className="p-3">Runtime</th>
                          <th className="p-3">Size</th>
                        </tr>
                      </thead>
                      <tbody>
                        {video.versions.map(version => (
                          <tr key={version.id} className="border-b">
                            <td className="p-3">
                              <div className="font-medium">
                                {version.file_name}
                                {version.is_primary ? " · Primary" : ""}
                              </div>
                              <div className="max-w-[440px] truncate text-xs text-muted-foreground">
                                {version.relative_path}
                              </div>
                            </td>
                            <td className="p-3">
                              {version.video_codec || "—"}
                              {version.width && version.height
                                ? ` · ${version.width}×${version.height}`
                                : ""}
                            </td>
                            <td className="p-3 tabular-nums">
                              {formatDuration(version.duration_seconds)}
                            </td>
                            <td className="p-3 tabular-nums">
                              {formatBytes(version.size_bytes)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    {video.source_url && (
                      <a
                        href={video.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                      >
                        Open source video
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    )}
                  </div>

                  <Button
                    type="button"
                    onClick={() => onOpenMediaDetails(video.media_item_id)}
                  >
                    Open Media Details
                  </Button>
                </div>
              </div>
            </ScrollableDialogBody>
          </>
        )}
      </ScrollableDialogContent>
    </Dialog>
  )
}


export function OnlineVideoCatalog({
  library,
}: {
  library: Library
}) {
  const [view, setView] = useState<OnlineVideoView>("channels")
  const [selectedChannel, setSelectedChannel] = useState<OnlineVideoChannel | null>(null)
  const [selectedPlaylist, setSelectedPlaylist] = useState<OnlineVideoPlaylist | null>(null)
  const [selectedVideo, setSelectedVideo] = useState<OnlineVideoCatalogItem | null>(null)
  const [selectedMediaItemId, setSelectedMediaItemId] = useState<string | null>(null)

  const refreshKey = useMemo(
    () => library.last_scanned_at ?? library.updated_at,
    [library.last_scanned_at, library.updated_at],
  )

  function openVideo(video: OnlineVideoCatalogItem) {
    setSelectedChannel(null)
    setSelectedPlaylist(null)
    setSelectedVideo(video)
  }

  function openMediaDetails(mediaItemId: string) {
    setSelectedVideo(null)
    setSelectedMediaItemId(mediaItemId)
  }

  return (
    <>
      <div className="space-y-4">
        <div className="text-sm text-muted-foreground">
          Browse online video semantically by channel, playlist, or individual video. Physical TubeArchivist paths remain unchanged.
        </div>

        <Tabs
          value={view}
          onValueChange={value => setView(value as OnlineVideoView)}
        >
          <TabsList>
            <TabsTrigger value="channels">
              Channels
            </TabsTrigger>
            <TabsTrigger value="playlists">
              Playlists
            </TabsTrigger>
            <TabsTrigger value="videos">
              Videos
            </TabsTrigger>
          </TabsList>

          <TabsContent value="channels" className="mt-4">
            <ChannelCatalog
              library={library}
              refreshKey={refreshKey}
              onOpenChannel={setSelectedChannel}
            />
          </TabsContent>

          <TabsContent value="playlists" className="mt-4">
            <PlaylistCatalog
              library={library}
              refreshKey={refreshKey}
              onOpenPlaylist={setSelectedPlaylist}
            />
          </TabsContent>

          <TabsContent value="videos" className="mt-4">
            <VideoCatalog
              library={library}
              refreshKey={refreshKey}
              onOpenVideo={setSelectedVideo}
            />
          </TabsContent>
        </Tabs>
      </div>

      <ChannelDialog
        channel={selectedChannel}
        onClose={() => setSelectedChannel(null)}
        onOpenVideo={openVideo}
      />

      <PlaylistDialog
        playlist={selectedPlaylist}
        onClose={() => setSelectedPlaylist(null)}
        onOpenVideo={openVideo}
      />

      <VideoDialog
        video={selectedVideo}
        onClose={() => setSelectedVideo(null)}
        onOpenMediaDetails={openMediaDetails}
      />

      <MediaDetailDialog
        mediaItemId={selectedMediaItemId}
        onClose={() => setSelectedMediaItemId(null)}
      />
    </>
  )
}
