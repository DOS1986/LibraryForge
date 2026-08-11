export interface PaginatedResponse<T> {
  count: number
  page: number
  page_size: number
  total_pages: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface OnlineVideoChannel {
  id: string
  library: string
  provider: string
  source_id: string
  semantic_key: string
  title: string
  sort_title: string
  handle: string
  description: string
  source_url: string
  external_ids: Record<string, string>
  canonical_metadata: Record<string, unknown>
  locked: boolean
  video_count: number
  runtime_seconds: number
  storage_bytes: number
  last_upload_date: string | null
  created_at: string
  updated_at: string
}

export interface OnlineVideoPlaylistSummary {
  id: string
  channel_id: string | null
  channel_title: string | null
  provider: string
  source_id: string
  semantic_key: string
  title: string
  source_url: string
  playlist_kind: "remote" | "custom" | "unknown"
}

export interface OnlineVideoPlaylist extends OnlineVideoPlaylistSummary {
  library: string
  description: string
  external_ids: Record<string, string>
  canonical_metadata: Record<string, unknown>
  locked: boolean
  video_count: number
  runtime_seconds: number
  storage_bytes: number
  created_at: string
  updated_at: string
}

export interface OnlineVideoVersion {
  id: string
  name: string
  edition: string
  is_primary: boolean
  file_id: string
  file_name: string
  relative_path: string
  size_bytes: number
  duration_seconds: number | null
  video_codec: string
  width: number | null
  height: number | null
}

export interface OnlineVideoPlaylistMembership {
  id: string
  position: number | null
  playlist: OnlineVideoPlaylistSummary
}

export interface OnlineVideoCatalogItem {
  id: string
  library: string
  media_item_id: string
  title: string
  description: string
  release_date: string | null
  semantic_key: string
  channel_id: string | null
  channel_title: string | null
  channel_handle: string | null
  provider: string
  source_id: string
  source_url: string
  upload_date: string | null
  video_kind: "video" | "short" | "stream" | "unknown"
  tags: string[]
  categories: string[]
  external_ids: Record<string, string>
  canonical_metadata: Record<string, unknown>
  locked: boolean
  runtime_seconds: number | null
  storage_bytes: number
  version_count: number
  playlist_count: number
  versions: OnlineVideoVersion[]
  playlists: OnlineVideoPlaylistMembership[]
  created_at: string
  updated_at: string
}

interface CatalogQuery {
  libraryId: string
  search?: string
  ordering?: string
  page?: number
  pageSize?: number
  channelId?: string
  playlistId?: string
  provider?: string
  kind?: string
  uploadedAfter?: string
  uploadedBefore?: string
}

async function readJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    method: "GET",
    credentials: "include",
    headers: {
      Accept: "application/json",
    },
  })

  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`

    try {
      const data = await response.json() as Record<string, unknown>

      if (typeof data.detail === "string") {
        message = data.detail
      } else {
        const first = Object.entries(data)[0]
        if (first) {
          const [field, value] = first
          message = Array.isArray(value)
            ? `${field}: ${String(value[0])}`
            : `${field}: ${String(value)}`
        }
      }
    } catch {
      // Keep the HTTP fallback message.
    }

    throw new Error(message)
  }

  return await response.json() as T
}

function queryString(query: CatalogQuery) {
  const params = new URLSearchParams({
    library: query.libraryId,
    page: String(query.page ?? 1),
    page_size: String(query.pageSize ?? 20),
  })

  if (query.search?.trim()) {
    params.set("search", query.search.trim())
  }

  if (query.ordering) {
    params.set("ordering", query.ordering)
  }

  if (query.channelId) {
    params.set("channel", query.channelId)
  }

  if (query.playlistId) {
    params.set("playlist", query.playlistId)
  }

  if (query.provider) {
    params.set("provider", query.provider)
  }

  if (query.kind) {
    params.set("kind", query.kind)
  }

  if (query.uploadedAfter) {
    params.set("uploaded_after", query.uploadedAfter)
  }

  if (query.uploadedBefore) {
    params.set("uploaded_before", query.uploadedBefore)
  }

  return params.toString()
}

export async function getOnlineVideoChannels(query: CatalogQuery) {
  return readJson<PaginatedResponse<OnlineVideoChannel>>(
    `/api/catalog-channels/?${queryString(query)}`,
  )
}

export async function getOnlineVideoPlaylists(query: CatalogQuery) {
  return readJson<PaginatedResponse<OnlineVideoPlaylist>>(
    `/api/catalog-playlists/?${queryString(query)}`,
  )
}

export async function getOnlineVideos(query: CatalogQuery) {
  return readJson<PaginatedResponse<OnlineVideoCatalogItem>>(
    `/api/catalog-online-videos/?${queryString(query)}`,
  )
}
