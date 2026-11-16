import type {
  ArtworkRefreshResult,
  CatalogEditorArtwork,
  CatalogEditorDetail,
  CatalogEditorKind,
  CatalogEditorVersion,
  CatalogEpisode,
  CatalogMetadataUpdate,
  CatalogMovie,
  CatalogVersionUpdate,
  CatalogSeason,
  CatalogSeries,
  Library,
  LibraryAsset,
  LibraryBrowserResponse,
  LibraryContentType,
  ManagementMode,
  MediaFile,
  MediaItemDetail,
  MetadataMatchApplyRequest,
  MetadataMatchApplyResult,
  MetadataMatchContext,
  MetadataMatchKind,
  MetadataMatchPreview,
  MetadataMatchSearchResult,
  MetadataSource,
  NfoExportBatch,
  NfoExportPreview,
  NfoImportPreview,
  RatingCoverage,
  RatingKind,
  RatingSuggestions,
  NfoFile,
  NfoValidation,
  OutputProfile,
  Paginated,
  Projection,
  RestartRequestResult,
  ScanJob,
  ScanWorkerStatus,
  SemanticMatch,
  SemanticResetResult,
  SemanticResolveInput,
  StorageTestResult,
  SystemHealth,
  SystemStatus,
  SystemVersionInfo,
  User,
  UserSettings,
  UserSettingsUpdate,
  YouTubeHintApplyResult,
  YouTubeRatingHints,
  ArtworkChoices,
  ArtworkSaveResult,
  Paged,
  PlanActionRow,
  ProjectionPlanDetail,
  ProjectionRunDetail,
  ProjectionRunsSummary,
  RunJournalRow,
  ChannelEditorDetail,
  NfoComparison,
  NfoSyncKind,
  NfoWriteResult,
  OnlineVideoEditorDetail,
} from "@/types"


export class ApiError extends Error {
  status: number
  // The server's machine-readable reason, when it sent one (for example "existing_artwork").
  code: string | null

  constructor(
    message: string,
    status: number,
    code: string | null = null,
  ) {
    super(message)

    this.name = "ApiError"
    this.status = status
    this.code = code
  }
}


function getCookie(
  name: string,
) {
  const cookies =
    document.cookie.split(";")

  for (const cookie of cookies) {
    const trimmed =
      cookie.trim()

    if (
      trimmed.startsWith(
        `${name}=`
      )
    ) {
      return decodeURIComponent(
        trimmed.substring(
          name.length + 1
        )
      )
    }
  }

  return null
}


function extractErrorMessage(
  data: unknown,
  fallback: string,
) {
  if (
    data
    && typeof data === "object"
  ) {
    const record =
      data as Record<
        string,
        unknown
      >

    if (
      typeof record.detail
      === "string"
    ) {
      return record.detail
    }

    for (
      const [
        field,
        value,
      ]
      of Object.entries(
        record
      )
    ) {
      if (
        Array.isArray(value)
        && value.length > 0
        && typeof value[0]
          === "string"
      ) {
        return (
          `${field}: ${value[0]}`
        )
      }

      if (
        typeof value
        === "string"
      ) {
        return (
          `${field}: ${value}`
        )
      }
    }
  }

  return fallback
}


async function request<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (
    options.method
    ?? "GET"
  ).toUpperCase()

  const headers =
    new Headers(
      options.headers
    )

  if (options.body) {
    headers.set(
      "Content-Type",
      "application/json",
    )
  }

  if (
    ![
      "GET",
      "HEAD",
      "OPTIONS",
    ].includes(method)
  ) {
    const csrfToken =
      getCookie(
        "csrftoken"
      )

    if (csrfToken) {
      headers.set(
        "X-CSRFToken",
        csrfToken,
      )
    }
  }

  const response =
    await fetch(
      url,
      {
        ...options,
        headers,
        credentials: "include",
      },
    )

  const text =
    await response.text()

  let data: unknown =
    undefined

  if (text) {
    try {
      data = JSON.parse(
        text
      )
    } catch {
      data =
        undefined
    }
  }

  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(
        data,
        text
        || (
          "Request failed with "
          + `status ${response.status}.`
        ),
      ),
      response.status,
      data && typeof data === "object" && typeof (data as { code?: unknown }).code === "string"
        ? (data as { code: string }).code
        : null,
    )
  }

  return data as T
}


export async function ensureCsrf() {
  await request(
    "/api/auth/csrf/",
  )
}


export async function getMe() {
  return request<{
    user: User
  }>(
    "/api/auth/me/",
  )
}


export async function login(
  email: string,
  password: string,
) {
  await ensureCsrf()

  return request<{
    user: User
  }>(
    "/api/auth/login/",
    {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
      }),
    },
  )
}


export async function logout() {
  await ensureCsrf()

  return request(
    "/api/auth/logout/",
    {
      method: "POST",
    },
  )
}


export async function getLibraries() {
  return request<Library[]>(
    "/api/libraries/",
  )
}


export async function createLibrary(
  input: {
    name: string
    path: string
    management_mode:
      ManagementMode

    content_type:
      LibraryContentType
  },
) {
  await ensureCsrf()

  return request<Library>(
    "/api/libraries/",
    {
      method: "POST",
      body: JSON.stringify(
        input
      ),
    },
  )
}


export async function updateLibrarySettings(
  libraryId: string,
  input: {
    content_type?:
      LibraryContentType

    management_mode?:
      ManagementMode
  },
) {
  await ensureCsrf()

  return request<Library>(
    `/api/libraries/${libraryId}/`,
    {
      method: "PATCH",
      body: JSON.stringify(
        input
      ),
    },
  )
}


export async function testLibraryPath(
  path: string,
) {
  await ensureCsrf()

  return request<
    StorageTestResult
  >(
    "/api/libraries/test-path/",
    {
      method: "POST",
      body: JSON.stringify({
        path,
      }),
    },
  )
}


export async function startLibraryScan(
  libraryId: string,
) {
  await ensureCsrf()

  return request<ScanJob>(
    `/api/libraries/${libraryId}/scan/`,
    {
      method: "POST",
    },
  )
}


export async function getScanJob(
  jobId: string,
) {
  return request<ScanJob>(
    `/api/scan-jobs/${jobId}/`,
  )
}


// Queued or stalled scans stop immediately; a running scan stops at its
// worker's next progress checkpoint.
export async function cancelScanJob(
  jobId: string,
) {
  await ensureCsrf()

  return request<ScanJob>(
    `/api/scan-jobs/${jobId}/cancel/`,
    {
      method: "POST",
    },
  )
}


export async function getScanWorkerStatus() {
  return request<ScanWorkerStatus>(
    "/api/scan-jobs/worker/",
  )
}



export async function getScanJobs(
  libraryId?: string,
  page = 1,
  pageSize = 20,
) {
  const params =
    new URLSearchParams({
      page:
        String(page),

      page_size:
        String(pageSize),
    })

  if (libraryId) {
    params.set(
      "library",
      libraryId,
    )
  }

  return request<
    Paginated<ScanJob>
  >(
    `/api/scan-jobs/?${params.toString()}`,
  )
}


export async function getMediaFiles(
  libraryId: string,
  ordering = "media_item__title",
  search = "",
  page = 1,
  pageSize = 20,
) {
  const params =
    new URLSearchParams({
      library:
        libraryId,

      ordering,

      page:
        String(page),

      page_size:
        String(pageSize),
    })

  if (search.trim()) {
    params.set(
      "search",
      search.trim(),
    )
  }

  return request<
    Paginated<MediaFile>
  >(
    `/api/media-files/?${params.toString()}`,
  )
}


export async function getLibraryAssets(
  libraryId: string,
  ordering = "relative_path",
  search = "",
  page = 1,
  pageSize = 20,
) {
  const params =
    new URLSearchParams({
      library:
        libraryId,

      ordering,

      page:
        String(page),

      page_size:
        String(pageSize),
    })

  if (search.trim()) {
    params.set(
      "search",
      search.trim(),
    )
  }

  return request<
    Paginated<LibraryAsset>
  >(
    `/api/library-assets/?${params.toString()}`,
  )
}


export async function getLibraryBrowser(
  libraryId: string,
  path = "",
  content:
    | "media"
    | "files"
    | "nfo"
    = "media",
  ordering = "name",
  search = "",
  page = 1,
  pageSize = 20,
) {
  const params =
    new URLSearchParams({
      library:
        libraryId,

      path,

      content,

      ordering,

      page:
        String(page),

      page_size:
        String(pageSize),
    })

  if (search.trim()) {
    params.set(
      "search",
      search.trim(),
    )
  }

  return request<
    LibraryBrowserResponse
  >(
    `/api/library-browser/?${params.toString()}`,
  )
}


export async function getNfoFile(
  nfoId: string,
) {
  return request<NfoFile>(
    `/api/nfo-files/${nfoId}/`,
  )
}


export async function getMediaItem(
  mediaItemId: string,
) {
  return request<
    MediaItemDetail
  >(
    `/api/media-items/${mediaItemId}/`,
  )
}


export async function getNfoFiles(
  libraryId: string,
  ordering = "relative_path",
  search = "",
  page = 1,
  pageSize = 20,
) {
  const params =
    new URLSearchParams({
      library:
        libraryId,

      ordering,

      page:
        String(page),

      page_size:
        String(pageSize),
    })

  if (search.trim()) {
    params.set(
      "search",
      search.trim(),
    )
  }

  return request<
    Paginated<NfoFile>
  >(
    `/api/nfo-files/?${params.toString()}`,
  )
}


export async function updateNfoFile(
  nfoId: string,
  rawXml: string,
) {
  await ensureCsrf()

  return request<NfoFile>(
    `/api/nfo-files/${nfoId}/`,
    {
      method: "PATCH",
      body: JSON.stringify({
        raw_xml:
          rawXml,
      }),
    },
  )
}


export async function validateNfo(
  rawXml: string,
) {
  await ensureCsrf()

  return request<
    NfoValidation
  >(
    "/api/nfo-files/validate/",
    {
      method: "POST",
      body: JSON.stringify({
        raw_xml:
          rawXml,
      }),
    },
  )
}


export async function getMetadataSources(
  libraryId: string,
  sourceType?: string,
  status?: string,
  page = 1,
  pageSize = 20,
) {
  const params =
    new URLSearchParams({
      library:
        libraryId,

      ordering:
        "media_item__title",

      page:
        String(page),

      page_size:
        String(pageSize),
    })

  if (sourceType) {
    params.set(
      "source_type",
      sourceType,
    )
  }

  if (status) {
    params.set(
      "status",
      status,
    )
  }

  return request<
    Paginated<MetadataSource>
  >(
    `/api/metadata-sources/?${params.toString()}`,
  )
}


export async function getCatalogMovies(
  libraryId: string,
  search = "",
  ordering = "title",
  page = 1,
  pageSize = 20,
) {
  const params =
    new URLSearchParams({
      library:
        libraryId,

      ordering,

      page:
        String(page),

      page_size:
        String(pageSize),
    })

  if (search.trim()) {
    params.set(
      "search",
      search.trim(),
    )
  }

  return request<
    Paginated<CatalogMovie>
  >(
    `/api/catalog-movies/?${params.toString()}`,
  )
}


export async function getCatalogMovie(
  movieId: string,
) {
  return request<
    CatalogMovie
  >(
    `/api/catalog-movies/${movieId}/`,
  )
}


export async function getCatalogSeries(
  libraryId: string,
  search = "",
  ordering = "sort_title",
  page = 1,
  pageSize = 20,
) {
  const params =
    new URLSearchParams({
      library:
        libraryId,

      ordering,

      page:
        String(page),

      page_size:
        String(pageSize),
    })

  if (search.trim()) {
    params.set(
      "search",
      search.trim(),
    )
  }

  return request<
    Paginated<CatalogSeries>
  >(
    `/api/catalog-series/?${params.toString()}`,
  )
}


export async function getCatalogSeasons(
  seriesId: string,
  page = 1,
  pageSize = 100,
) {
  const params =
    new URLSearchParams({
      series:
        seriesId,

      ordering:
        "season_number",

      page:
        String(page),

      page_size:
        String(pageSize),
    })

  return request<
    Paginated<CatalogSeason>
  >(
    `/api/catalog-seasons/?${params.toString()}`,
  )
}


export async function getCatalogEpisodes(
  seasonId: string,
  search = "",
  ordering = "episode_number",
  page = 1,
  pageSize = 20,
) {
  const params =
    new URLSearchParams({
      season:
        seasonId,

      ordering,

      page:
        String(page),

      page_size:
        String(pageSize),
    })

  if (search.trim()) {
    params.set(
      "search",
      search.trim(),
    )
  }

  return request<
    Paginated<CatalogEpisode>
  >(
    `/api/catalog-episodes/?${params.toString()}`,
  )
}


export async function getSemanticMatches(
  libraryId: string,
  status?: string,
  page = 1,
  pageSize = 20,
) {
  return getSemanticMatchPage(
    libraryId,
    {
      status,
      page,
      pageSize,
    },
  )
}


export async function getSemanticMatchPage(
  libraryId: string,
  options: {
    status?: string
    locked?: boolean
    attention?: boolean
    search?: string
    ordering?: string
    page?: number
    pageSize?: number
  } = {},
) {
  const params =
    new URLSearchParams({
      library:
        libraryId,

      page:
        String(
          options.page
          ?? 1
        ),

      page_size:
        String(
          options.pageSize
          ?? 20
        ),

      ordering:
        options.ordering
        ?? "-updated_at",
    })

  if (options.status) {
    params.set(
      "status",
      options.status,
    )
  }

  if (
    options.locked
    !== undefined
  ) {
    params.set(
      "locked",
      String(
        options.locked
      ),
    )
  }

  if (options.attention) {
    params.set(
      "attention",
      "true",
    )
  }

  if (
    options.search
    ?.trim()
  ) {
    params.set(
      "search",
      options.search.trim(),
    )
  }

  return request<
    Paginated<SemanticMatch>
  >(
    `/api/semantic-matches/?${params.toString()}`,
  )
}


export async function resolveSemanticMatch(
  matchId: string,
  input: SemanticResolveInput,
) {
  await ensureCsrf()

  return request<
    SemanticMatch
  >(
    `/api/semantic-matches/${matchId}/resolve/`,
    {
      method:
        "POST",

      body:
        JSON.stringify(
          input
        ),
    },
  )
}


export async function setSemanticMatchLock(
  matchId: string,
  locked: boolean,
) {
  await ensureCsrf()

  return request<
    SemanticMatch
  >(
    `/api/semantic-matches/${matchId}/set-lock/`,
    {
      method:
        "POST",

      body:
        JSON.stringify({
          locked,
        }),
    },
  )
}


export async function resetSemanticMatch(
  matchId: string,
) {
  await ensureCsrf()

  return request<
    SemanticResetResult
  >(
    `/api/semantic-matches/${matchId}/reset/`,
    {
      method:
        "POST",
    },
  )
}


export async function getOutputProfiles() {
  return request<
    OutputProfile[]
  >(
    "/api/output-profiles/",
  )
}


export async function createOutputProfile(
  input: {
    name: string
    target:
      | "jellyfin"
      | "emby"
      | "kodi"
      | "generic"
    nfo_root_element: string
  },
) {
  await ensureCsrf()

  return request<
    OutputProfile
  >(
    "/api/output-profiles/",
    {
      method: "POST",
      body: JSON.stringify(
        input
      ),
    },
  )
}


export async function getProjections(
  libraryId: string,
) {
  const params =
    new URLSearchParams({
      library:
        libraryId,
    })

  return request<
    Projection[]
  >(
    `/api/projections/?${params.toString()}`,
  )
}


// Channels as TV shows: a Jellyfin-ready folder of hardlinked, renamed videos.
export async function getYouTubeShows(libraryId: string) {
  return request<Projection[]>(`/api/libraries/${libraryId}/youtube-shows/`)
}


export async function createYouTubeShows(libraryId: string, destinationPath: string, hardlinkAcknowledged: boolean) {
  await ensureCsrf()

  return request<Projection>(
    `/api/libraries/${libraryId}/youtube-shows/`,
    {
      method: "POST",
      body: JSON.stringify({ destination_path: destinationPath, hardlink_acknowledged: hardlinkAcknowledged }),
    },
  )
}


// Every projection of a library, and creating one (layout follows the library's type).
export async function getLibraryProjections(libraryId: string) {
  return request<Projection[]>(`/api/libraries/${libraryId}/projections/`)
}


export async function createLibraryProjection(
  libraryId: string,
  input: {
    destination_path?: string
    layout?: "movies" | "tv" | "youtube_shows" | "library_nfo"
    link_mode?: Projection["link_mode"]
    hardlink_acknowledged?: boolean
    target?: "jellyfin" | "emby" | "kodi" | "generic"
  },
) {
  await ensureCsrf()
  return request<Projection>(`/api/libraries/${libraryId}/projections/`, { method: "POST", body: JSON.stringify(input) })
}


// Projection settings (never touches disk).
export async function updateProjection(
  projectionId: string,
  values: Partial<Pick<Projection, "stale_policy" | "hardlink_acknowledged" | "enabled" | "output_profile">>,
) {
  await ensureCsrf()
  return request<Projection>(`/api/projections/${projectionId}/`, { method: "PATCH", body: JSON.stringify(values) })
}


export async function deleteProjection(projectionId: string) {
  await ensureCsrf()
  return request<null>(`/api/projections/${projectionId}/`, { method: "DELETE" })
}


// Build a stored plan to review. Reads only; changes nothing on disk.
export async function buildProjectionPlan(projectionId: string, channel?: string) {
  await ensureCsrf()
  return request<ProjectionPlanDetail>(`/api/projections/${projectionId}/plans/`, {
    method: "POST",
    body: JSON.stringify(channel ? { channel } : {}),
  })
}


export async function getProjectionPlanActions(planId: string, page: number, action?: string) {
  return request<Paged<PlanActionRow>>(
    `/api/projection-plans/${planId}/actions/` + queryString({ page, action: action || undefined }),
  )
}


// Apply exactly the reviewed plan in the background worker.
export async function requestProjectionRun(planId: string, digest: string, idempotencyKey: string) {
  await ensureCsrf()
  return request<ProjectionRunDetail>(`/api/projection-plans/${planId}/runs/`, {
    method: "POST",
    body: JSON.stringify({ digest, idempotency_key: idempotencyKey }),
  })
}


export async function getProjectionRun(runId: string) {
  return request<ProjectionRunDetail>(`/api/projection-runs/${runId}/`)
}


export async function cancelProjectionRun(runId: string) {
  await ensureCsrf()
  return request<ProjectionRunDetail>(`/api/projection-runs/${runId}/cancel/`, { method: "POST" })
}


export async function getProjectionRuns(projectionId: string) {
  return request<ProjectionRunsSummary>(`/api/projections/${projectionId}/runs/`)
}


export async function getProjectionRunJournal(runId: string, problemsOnly = true) {
  return request<Paged<RunJournalRow>>(
    `/api/projection-runs/${runId}/actions/` + queryString({ problems: problemsOnly ? 1 : undefined, page_size: 200 }),
  )
}


export async function getSystemVersion() {
  return request<
    SystemVersionInfo
  >(
    "/api/system/version/",
  )
}


function catalogEditorPath(
  kind: CatalogEditorKind,
  id: string,
) {
  const plural = (
    kind === "series"
      ? "series"
      : kind === "movie"
        ? "movies"
        : kind === "season"
          ? "seasons"
          : "episodes"
  )

  return (
    `/api/catalog-editor/${plural}/${id}/`
  )
}


export async function getCatalogEditorDetail(
  kind: CatalogEditorKind,
  id: string,
) {
  return request<
    CatalogEditorDetail
  >(
    catalogEditorPath(
      kind,
      id,
    ),
  )
}


export async function updateCatalogEditorMetadata(
  kind: CatalogEditorKind,
  id: string,
  input: CatalogMetadataUpdate,
) {
  await ensureCsrf()

  return request<
    CatalogEditorDetail
  >(
    catalogEditorPath(
      kind,
      id,
    ),
    {
      method:
        "PATCH",

      body:
        JSON.stringify(
          input
        ),
    },
  )
}


export async function updateCatalogVersion(
  versionId: string,
  input: CatalogVersionUpdate,
) {
  await ensureCsrf()

  return request<
    CatalogEditorVersion
  >(
    `/api/catalog-editor/versions/${versionId}/`,
    {
      method:
        "PATCH",

      body:
        JSON.stringify(
          input
        ),
    },
  )
}


export async function makeCatalogVersionPrimary(
  versionId: string,
) {
  await ensureCsrf()

  return request<
    CatalogEditorVersion
  >(
    `/api/catalog-editor/versions/${versionId}/make-primary/`,
    {
      method:
        "POST",
    },
  )
}


export async function selectCatalogArtwork(
  artworkId: string,
) {
  await ensureCsrf()

  return request<
    CatalogEditorArtwork
  >(
    `/api/artwork-files/${artworkId}/select/`,
    {
      method: "POST",
    },
  )
}


export async function refreshLibraryArtwork(
  libraryId: string,
) {
  await ensureCsrf()

  return request<
    ArtworkRefreshResult
  >(
    `/api/libraries/${libraryId}/artwork/refresh/`,
    {
      method: "POST",
    },
  )
}




export async function getUserSettings() {
  return request<UserSettings>(
    "/api/preferences/settings/",
  )
}


export async function updateUserSettings(
  input: UserSettingsUpdate,
) {
  await ensureCsrf()

  return request<UserSettings>(
    "/api/preferences/settings/",
    {
      method: "PATCH",
      body: JSON.stringify(input),
    },
  )
}


export async function getSystemHealth() {
  return request<SystemHealth>(
    "/api/system/health/",
  )
}


export async function getSystemStatus() {
  return request<SystemStatus>(
    "/api/system/status/",
  )
}


export async function requestSystemRestart() {
  await ensureCsrf()

  return request<RestartRequestResult>(
    "/api/system/restart/",
    {
      method: "POST",
    },
  )
}


// Metadata provider matching. GET only: these never change catalog data.

function metadataMatchPath(
  kind: MetadataMatchKind,
  id: string,
  action = "",
) {
  return (
    `/api/metadata-match/${kind}/${id}/`
    + (action ? `${action}/` : "")
  )
}


function queryString(
  params: Record<string, string | number | null | undefined>,
) {
  const search = new URLSearchParams()

  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      search.set(key, String(value))
    }
  }

  const text = search.toString()

  return text ? `?${text}` : ""
}


export async function getMetadataMatchContext(
  kind: MetadataMatchKind,
  id: string,
) {
  return request<MetadataMatchContext>(
    metadataMatchPath(kind, id),
  )
}


export async function searchMetadataMatch(
  kind: MetadataMatchKind,
  id: string,
  params: {
    connection?: string
    query?: string
    year?: string
    page?: number
  },
) {
  return request<MetadataMatchSearchResult>(
    metadataMatchPath(kind, id, "search") + queryString(params),
  )
}


export async function previewMetadataMatch(
  kind: MetadataMatchKind,
  id: string,
  params: {
    connection?: string
    source_id: string
    territory?: string
  },
) {
  return request<MetadataMatchPreview>(
    metadataMatchPath(kind, id, "preview") + queryString(params),
  )
}


// Online videos and channels: hand edits are locked against later scans.
export async function getOnlineVideoEditor(id: string) {
  return request<OnlineVideoEditorDetail>(`/api/catalog-editor/online-videos/${id}/`)
}


export async function updateOnlineVideoEditor(id: string, values: Record<string, unknown>) {
  await ensureCsrf()
  return request<OnlineVideoEditorDetail>(`/api/catalog-editor/online-videos/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(values),
  })
}


export async function getChannelEditor(id: string) {
  return request<ChannelEditorDetail>(`/api/catalog-editor/channels/${id}/`)
}


export async function updateChannelEditor(id: string, values: Record<string, unknown>) {
  await ensureCsrf()
  return request<ChannelEditorDetail>(`/api/catalog-editor/channels/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(values),
  })
}


// LibraryForge's fields compared with the item's NFO.
export async function getItemNfo(kind: NfoSyncKind, id: string) {
  return request<NfoComparison>(`/api/catalog-editor/${kind}/${id}/nfo/`)
}


// Writes the chosen fields into the NFO (or creates it). Omit fields for every difference.
export async function writeItemNfo(kind: NfoSyncKind, id: string, fields?: string[]) {
  await ensureCsrf()
  return request<NfoWriteResult>(`/api/catalog-editor/${kind}/${id}/nfo/`, {
    method: "POST",
    body: JSON.stringify(fields ? { fields } : {}),
  })
}


// Artwork a source offers for this title. Never writes anything.
export async function getMatchArtwork(
  kind: MetadataMatchKind,
  id: string,
  params: {
    connection?: string
    prefer?: string
    source_id?: string
    tmdb?: string
    imdb?: string
    tvdb?: string
  },
) {
  return request<ArtworkChoices>(metadataMatchPath(kind, id, "artwork") + queryString(params))
}


// Saves one offered image beside the item; the server re-checks it is offered.
export async function saveMatchArtwork(
  kind: MetadataMatchKind,
  id: string,
  body: {
    connection: string
    source_id?: string
    ids?: Record<string, string>
    url: string
    replace?: boolean
    operation_id: string
  },
) {
  await ensureCsrf()

  return request<ArtworkSaveResult>(
    metadataMatchPath(kind, id, "artwork"),
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  )
}


// The only metadata-match call that changes the catalog. The server rebuilds
// and re-validates the reviewed preview; only field names are sent.
export async function applyMetadataMatch(
  kind: MetadataMatchKind,
  id: string,
  body: MetadataMatchApplyRequest,
) {
  await ensureCsrf()

  return request<MetadataMatchApplyResult>(
    metadataMatchPath(kind, id, "apply"),
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  )
}


export async function getLibraryRatings(
  libraryId: string,
  params: {
    kind: RatingKind
    status?: string
    search?: string
    page?: number
    page_size?: number
  },
) {
  return request<RatingCoverage>(
    `/api/libraries/${libraryId}/ratings/` + queryString(params),
  )
}


// Read-only: searches the provider and returns suggestions. Each rating is
// applied separately, through applyMetadataMatch, after the user confirms it.
export async function getRatingSuggestions(
  libraryId: string,
  kind: MetadataMatchKind,
  ids: string[],
) {
  return request<RatingSuggestions>(
    `/api/libraries/${libraryId}/ratings/suggestions/`
    + queryString({ kind, ids: ids.join(",") }),
  )
}


// Read-only preview of importing <mpaa> ratings from indexed NFO files.
export async function previewNfoRatingImport(
  libraryId: string,
  kind: MetadataMatchKind,
) {
  return request<NfoImportPreview>(
    `/api/libraries/${libraryId}/ratings/nfo-import/` + queryString({ kind }),
  )
}


// Fills empty (or NFO-sourced) ratings from NFO files. The server recomputes
// the plan, so ratings changed since the preview are never overwritten.
export async function applyNfoRatingImport(
  libraryId: string,
  kind: MetadataMatchKind,
) {
  await ensureCsrf()

  return request<NfoImportPreview>(
    `/api/libraries/${libraryId}/ratings/nfo-import/`,
    {
      method: "POST",
      body: JSON.stringify({ kind }),
    },
  )
}


// Read-only preview of writing catalog ratings into existing NFO files.
export async function previewNfoRatingExport(
  libraryId: string,
  kind: MetadataMatchKind,
) {
  return request<NfoExportPreview>(
    `/api/libraries/${libraryId}/ratings/nfo-export/` + queryString({ kind }),
  )
}


// Writes one batch of NFO rating changes, continuing after `cursor`.
export async function writeNfoRatingBatch(
  libraryId: string,
  kind: MetadataMatchKind,
  cursor: string | null,
  batch = 100,
) {
  await ensureCsrf()

  return request<NfoExportBatch>(
    `/api/libraries/${libraryId}/ratings/nfo-export/`,
    {
      method: "POST",
      body: JSON.stringify({ kind, cursor, batch }),
    },
  )
}


// Set (or clear, with "") the rating on chosen items. Recorded as manual
// edits, so imports and provider suggestions won't replace them.
// Rating hints for channels from YouTube's made-for-kids and age-restriction flags.
export async function getYouTubeRatingHints(libraryId: string, ids: string[]) {
  return request<YouTubeRatingHints>(
    `/api/libraries/${libraryId}/ratings/youtube-hints/` + queryString({ ids: ids.join(",") }),
  )
}


// Applies reviewed hints; the server recomputes each and writes only those still matching.
export async function applyYouTubeRatingHints(libraryId: string, hints: Record<string, string>) {
  await ensureCsrf()

  return request<YouTubeHintApplyResult>(
    `/api/libraries/${libraryId}/ratings/youtube-hints/`,
    {
      method: "POST",
      body: JSON.stringify({ hints }),
    },
  )
}


export async function setLibraryRatings(
  libraryId: string,
  kind: RatingKind,
  ids: string[],
  rating: string,
) {
  await ensureCsrf()

  return request<{
    library_id: string
    kind: RatingKind
    rating: string
    requested: number
    changed: number
    unchanged: number
  }>(
    `/api/libraries/${libraryId}/ratings/set/`,
    {
      method: "POST",
      body: JSON.stringify({ kind, ids, rating }),
    },
  )
}
