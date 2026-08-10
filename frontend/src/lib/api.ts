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
  MetadataSource,
  NfoFile,
  NfoValidation,
  OutputProfile,
  Paginated,
  Projection,
  ProjectionPreview,
  ProjectionRunResult,
  RestartRequestResult,
  ScanJob,
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
} from "@/types"


export class ApiError extends Error {
  status: number

  constructor(
    message: string,
    status: number,
  ) {
    super(message)

    this.name = "ApiError"
    this.status = status
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


export async function createProjection(
  input: {
    library: string
    output_profile: string
    name: string
    destination_path: string
    link_mode:
      | "symlink"
      | "hardlink"
      | "copy"
    naming_template: string
    generate_nfo: boolean
  },
) {
  await ensureCsrf()

  return request<
    Projection
  >(
    "/api/projections/",
    {
      method: "POST",
      body: JSON.stringify(
        input
      ),
    },
  )
}


export async function previewProjection(
  projectionId: string,
) {
  return request<
    ProjectionPreview
  >(
    `/api/projections/${projectionId}/preview/`,
  )
}


export async function runProjection(
  projectionId: string,
) {
  await ensureCsrf()

  return request<
    ProjectionRunResult
  >(
    `/api/projections/${projectionId}/run/`,
    {
      method: "POST",
    },
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
