export interface User {
  id: number
  email: string
  displayName: string
  firstName: string
  lastName: string
  isStaff: boolean
  isSuperuser: boolean
}

export type ManagementMode =
  | "full_control"
  | "sidecar_only"
  | "read_only"

export type LibraryContentType =
  | "auto"
  | "movies"
  | "tv"
  | "online_video"
  | "mixed"
  | "generic"

export interface Library {
  id: string
  name: string
  path: string
  management_mode: ManagementMode
  management_mode_label: string
  content_type: LibraryContentType
  content_type_label: string
  media_count: number
  last_scanned_at: string | null
  created_at: string
  updated_at: string
}

export interface MediaFile {
  id: string
  library: string
  media_item: string
  title: string
  media_type: string
  relative_path: string
  file_name: string
  extension: string
  size_bytes: number
  source_modified_at: string | null
  duration_seconds: number | null
  container_format: string
  bit_rate: number | null
  video_codec: string
  width: number | null
  height: number | null
  frame_rate: number | null
  audio_codec: string
  audio_channels: number | null
  probe_status: string
  probe_error: string
  is_present: boolean
  last_seen_at: string | null
}

export type MediaSort =
  | "media_item__title"
  | "video_codec"
  | "duration_seconds"
  | "size_bytes"
  | "source_modified_at"

export interface Paginated<T> {
  count: number
  page: number
  page_size: number
  total_pages: number
  next: string | null
  previous: string | null
  results: T[]
}

export type PageSize =
  | 10
  | 20
  | 50
  | 100

export interface LibraryAsset {
  id: string
  library: string
  media_item: string | null
  media_title: string | null
  asset_type:
    | "media"
    | "nfo"
    | "artwork"
  relative_path: string
  file_name: string
  size_bytes: number
  is_present: boolean
  metadata_status: string
}


export interface LibraryBrowserBreadcrumb {
  name: string
  path: string
}

export type LibraryBrowserContentMode =
  | "media"
  | "files"
  | "nfo"

export type LibraryBrowserSort =
  | "name"
  | "media_count"
  | "nfo_count"
  | "file_count"
  | "duration_seconds"
  | "size_bytes"

export interface LibraryBrowserFolder {
  entry_type: "folder"
  name: string
  title: string
  relative_path: string
  media_count: number
  nfo_count: number
  artwork_count: number
  file_count: number
  duration_seconds: number
  size_bytes: number
}

export interface LibraryBrowserFile {
  entry_type:
    | "media"
    | "nfo"
    | "artwork"
  id: string
  media_item: string | null
  name: string
  title: string
  relative_path: string
  media_count: number
  nfo_count: number
  artwork_count: number
  file_count: number
  size_bytes: number
  duration_seconds: number | null
  video_codec: string
  width: number | null
  height: number | null
  metadata_status: string
}

export type LibraryBrowserEntry =
  | LibraryBrowserFolder
  | LibraryBrowserFile

export interface LibraryBrowserResponse
  extends Paginated<LibraryBrowserEntry> {
  current_path: string
  breadcrumbs: LibraryBrowserBreadcrumb[]
  content_mode: LibraryBrowserContentMode
  ordering: string
}


export interface CatalogMediaVersion {
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

export interface CatalogMovie {
  id: string
  title: string
  year: number | null
  runtime_seconds: number | null
  storage_bytes: number
  version_count: number
  versions: CatalogMediaVersion[]
  canonical_metadata: Record<string, unknown>
}

export interface CatalogSeries {
  id: string
  library: string
  title: string
  sort_title: string
  start_year: number | null
  end_year: number | null
  description: string
  season_count: number
  episode_count: number
  runtime_seconds: number
  storage_bytes: number
  canonical_metadata: Record<string, unknown>
  locked: boolean
}

export interface CatalogSeason {
  id: string
  series_id: string
  series_title: string
  season_number: number
  title: string
  description: string
  episode_count: number
  runtime_seconds: number
  storage_bytes: number
  canonical_metadata: Record<string, unknown>
  locked: boolean
}

export interface CatalogEpisode {
  id: string
  media_item_id: string
  series_id: string
  series_title: string
  season: string
  season_number: number
  episode_number: number
  episode_end_number: number | null
  absolute_number: number | null
  title: string
  air_date: string | null
  runtime_seconds: number | null
  storage_bytes: number
  version_count: number
  versions: CatalogMediaVersion[]
  locked: boolean
}

export interface SemanticAssignment {
  kind:
    | "movie"
    | "episode"
    | "online_video"
  media_item_id: string
  title: string
  year?: number | null
  series_id?: string
  series_title?: string
  season_id?: string
  season_number?: number
  episode_number?: number
  episode_end_number?: number | null
  provider?: string
  source_id?: string
  semantic_key?: string
  channel_id?: string
  channel_title?: string
  channel_handle?: string
}

export interface OnlineVideoSemanticCandidate {
  kind: "online_video"
  provider: string
  source_id: string
  title: string
  source_url: string
  upload_date: string | null
  video_kind: string
  tags: string[]
  categories: string[]
  channel_id: string
  channel_title: string
  channel_handle: string
  channel_url: string
  channel_description: string
  confidence: number
}

export interface SemanticCandidate {
  kind:
    | "unknown"
    | "movie"
    | "episode"
  title: string
  year: number | null
  series_title: string
  series_year: number | null
  season_number: number | null
  episode_number: number | null
  episode_end_number: number | null
  episode_title: string
  edition: string
  source: string
  confidence: number
}

export interface SemanticMatch {
  id: string
  library_id: string
  library_name: string
  media_item_id: string
  media_title: string
  current_assignment: SemanticAssignment | null
  file_name: string
  relative_path: string
  size_bytes: number
  duration_seconds: number | null
  video_codec: string
  width: number | null
  height: number | null
  status:
    | "matched"
    | "unresolved"
    | "conflict"
    | "manual"
  status_label: string
  source:
    | "nfo"
    | "filename"
    | "folder"
    | "manual"
    | "tubearchivist"
    | "tubearchivist_path"
    | "yt_dlp"
    | ""
  source_label: string
  confidence: number
  candidate_data: Record<string, unknown>
  locked: boolean
  notes: string
  last_resolved_at: string | null
  created_at: string
  updated_at: string
}

export interface SemanticResolveInput {
  candidate_source:
    | "nfo"
    | "filename"
    | "suggested"
    | "tubearchivist"
    | "tubearchivist_path"
    | "yt_dlp"
    | "manual"
  lock?: boolean
  notes?: string
  kind?:
    | "movie"
    | "episode"
    | "online_video"
  title?: string
  year?: number | null
  edition?: string
  series_title?: string
  series_year?: number | null
  season_number?: number | null
  episode_number?: number | null
  episode_end_number?: number | null
  episode_title?: string
  provider?: string
  video_id?: string
  channel_id?: string
  channel_title?: string
  channel_handle?: string
  source_url?: string
  upload_date?: string | null
  video_kind?: string
}

export interface SemanticFieldProvenance {
  id: string
  target_type: string
  target_id: string
  field_name: string
  source: string
  source_label: string
  source_ref: string
  value_snapshot: unknown
  locked: boolean
  updated_by: string | null
  created_at: string
  updated_at: string
}

export interface SemanticProvenanceSource {
  id: string
  source_type: string
  source_type_label: string
  status: string
  status_label: string
  media_file_id: string
  file_name: string
  relative_path: string
  extracted_data: Record<string, unknown>
  error: string
  last_checked_at: string
}

export interface SemanticMatchProvenance {
  match: {
    id: string
    status: string
    status_label: string
    source: string
    source_label: string
    confidence: number
    locked: boolean
    notes: string
    last_resolved_at: string | null
  }
  file: {
    id: string
    file_name: string
    relative_path: string
  }
  current_identity: Record<string, unknown> | null
  field_states: Record<string, SemanticFieldProvenance[]>
  metadata_sources: SemanticProvenanceSource[]
  playlist_memberships: Array<Record<string, unknown>>
  candidate_data: Record<string, unknown>
}

export interface SemanticResetResult {
  result:
    | "matched"
    | "unresolved"
    | "conflict"
    | "locked"
  match: SemanticMatch
}

export type CapabilityStatus =
  | "passed"
  | "failed"
  | "not_tested"

export interface StorageCapability {
  status: CapabilityStatus
  detail: string
}

export interface StorageTestResult {
  path: string
  accessible: boolean
  capabilities: {
    path_exists: StorageCapability
    directory: StorageCapability
    read_access: StorageCapability
    media_access: StorageCapability
    write_access: StorageCapability
    sidecar_creation: StorageCapability
    rename: StorageCapability
    hardlink: StorageCapability
    symlink: StorageCapability
  }
  recommended_management_mode:
    | ManagementMode
    | null
}

export type ScanJobStatus =
  | "queued"
  | "discovering"
  | "running"
  | "completed"
  | "completed_with_errors"
  | "failed"
  | "cancelled"

export interface ScanJob {
  id: string
  library: string
  library_name: string
  status: ScanJobStatus
  status_label: string
  // Queued, and no scan worker is running to pick it up.
  waiting_for_worker: boolean
  // Looks active, but the worker running it has stopped.
  stalled: boolean
  cancel_requested: boolean
  total_files: number
  processed_files: number
  total_media_files: number
  processed_media_files: number
  total_nfo_files: number
  processed_nfo_files: number
  progress_percent: number
  current_path: string
  created_count: number
  updated_count: number
  skipped_count: number
  nfo_created_count: number
  nfo_updated_count: number
  error_count: number
  errors: Array<{
    path: string
    error: string
  }>
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export interface MetadataSource {
  id: string
  library_id: string
  media_item_id: string
  media_file_id: string
  media_title: string
  file_name: string
  relative_path: string
  source_type:
    | "filename"
    | "ffprobe"
    | "embedded"
    | "tubearchivist"
    | "yt_dlp"
    | "nfo"
  source_type_label: string
  status:
    | "detected"
    | "not_detected"
    | "not_found"
    | "error"
  status_label: string
  extracted_data: Record<string, unknown>
  error: string
  first_seen_at: string
  last_checked_at: string
}

export interface MediaItemDetail {
  id: string
  library: string
  title: string
  media_type: string
  media_type_label: string
  description: string
  release_date: string | null
  tags: string[]
  canonical_metadata: Record<string, unknown>
  files: MediaFile[]
  metadata_sources: MetadataSource[]
  created_at: string
  updated_at: string
}

export interface NfoFile {
  id: string
  library: string
  media_item: string | null
  media_file: string | null
  media_title: string | null
  relative_path: string
  file_name: string
  size_bytes: number
  modified_ns: number
  root_element: string
  title: string
  year: number | null
  raw_xml: string
  parsed_data: Record<string, unknown>
  parse_status:
    | "ok"
    | "error"
    | "unparsed"
  parse_error: string
  is_generated: boolean
  is_present: boolean
  last_seen_at: string | null
  management_mode: ManagementMode
  created_at: string
  updated_at: string
}

export interface NfoValidation {
  valid: boolean
  root_element: string
  title: string
  year: number | null
  parsed_data: Record<string, unknown>
  error: string
}

export interface OutputProfile {
  id: string
  name: string
  target:
    | "jellyfin"
    | "emby"
    | "kodi"
    | "generic"
  target_label: string
  nfo_root_element: string
  created_at: string
  updated_at: string
}

export interface Projection {
  id: string
  library: string
  output_profile: string
  output_profile_name: string
  output_target: string
  name: string
  destination_path: string
  layout: "template" | "youtube_shows"
  link_mode:
    | "symlink"
    | "hardlink"
    | "copy"
  link_mode_label: string
  naming_template: string
  generate_nfo: boolean
  last_run_at: string | null
  created_at: string
  updated_at: string
}

export type ShowsAction = "create" | "update" | "relink" | "replace" | "delete" | "artwork"

export type ShowsResult =
  | "created"
  | "updated"
  | "relinked"
  | "deleted"
  | "artwork"
  | "adopted"
  | "kept"
  | "conflict"
  | "failed"

export interface ShowsPlannedChange {
  action: ShowsAction
  kind: string
  path: string
  channel_id: string | null
  channel: string
}

export interface ShowsPlan {
  projection_id: string
  destination_path: string
  channel: string | null
  source_error: string | null
  destination_error: string | null
  artwork_available: boolean
  summary: Record<ShowsAction, number>
  pending: number
  files: Record<string, number>
  managed_files: number
  channels: {
    id: string
    title: string
    folder: string
    rating: string
    videos: number
    pending: number
  }[]
  actions: ShowsPlannedChange[]
  actions_truncated: boolean
  last_run_at: string | null
}

export interface ShowsProblem extends ShowsPlannedChange {
  result: ShowsResult
  message: string
}

export interface ShowsSyncBatch {
  projection_id: string
  counts: Record<ShowsResult, number>
  problems: ShowsProblem[]
  error: string | null
  next_cursor: string | null
  remaining: number
}

export interface ProjectionPreviewItem {
  media_file_id: string
  title: string
  source_path: string
  destination_media_path: string
  destination_nfo_path: string
  metadata: Record<string, unknown>
}

export interface ProjectionPreview {
  total: number
  preview_count: number
  items: ProjectionPreviewItem[]
}

export interface ProjectionRunResult {
  created: number
  already_exists: number
  error_count: number
  errors: Array<{
    media_file_id: string
    path: string
    error: string
  }>
}


export interface SystemVersionInfo {
  name: string
  version: string
  channel:
    | "development"
    | "stable"
  environment: string
  backend_package_version: string | null
  backend_version_consistent: boolean
  git_sha: string | null
  git_short_sha: string | null
  git_branch: string | null
  git_dirty: boolean | null
  build_time: string | null
  runtime_started_at: string
  python_version: string
  django_version: string
}


export type CatalogEditorKind =
  | "movie"
  | "series"
  | "season"
  | "episode"

export interface CanonicalFieldState {
  id: string
  target_type:
    | "media_item"
    | "series"
    | "season"
    | "episode"
    | "media_version"
  target_id: string
  field_name: string
  source:
    | "manual"
    | "nfo"
    | "filename"
    | "folder"
    | "ffprobe"
    | "embedded"
    | "tubearchivist"
    | "yt_dlp"
    | "system"
    | "provider"
  source_label: string
  source_ref: string
  value_snapshot: unknown
  locked: boolean
  updated_by: string | null
  created_at: string
  updated_at: string
}

export interface MetadataChangeSet {
  id: string
  target_type:
    | "media_item"
    | "series"
    | "season"
    | "episode"
    | "media_version"
  target_id: string
  source:
    | "manual"
    | "system"
    | "provider"
  source_label: string
  source_ref?: string
  changes: Record<
    string,
    {
      old: unknown
      new: unknown
    }
  >
  note: string
  changed_by: string | null
  changed_by_label: string | null
  created_at: string
}

export interface CatalogEditorVersion {
  id: string
  media_item_id: string
  file_id: string
  name: string
  edition: string
  notes: string
  is_primary: boolean
  file_name: string
  relative_path: string
  size_bytes: number
  duration_seconds: number | null
  container_format: string
  bit_rate: number | null
  video_codec: string
  width: number | null
  height: number | null
  audio_codec: string
  audio_channels: number | null
  metadata: Record<string, unknown>
}

export interface CatalogEditorSource {
  id: string
  source_type:
    | "filename"
    | "ffprobe"
    | "embedded"
    | "tubearchivist"
    | "yt_dlp"
    | "nfo"
  source_type_label: string
  status:
    | "detected"
    | "not_detected"
    | "not_found"
    | "error"
  status_label: string
  media_file_id: string
  file_name: string
  relative_path: string
  extracted_data: Record<string, unknown>
  error: string
  last_checked_at: string
}

export interface CatalogEditorNfoFile {
  id: string
  file_name: string
  relative_path: string
  root_element: string
  title: string
  year: number | null
  raw_xml: string
  parsed_data: Record<string, unknown>
  parse_status:
    | "ok"
    | "error"
    | "unparsed"
  parse_error: string
  is_generated: boolean
  is_present: boolean
  updated_at: string
}

export interface CatalogEditorContext {
  series_id?: string
  series_title?: string
  season_id?: string
  season_number?: number
  episode_number?: number
  episode_end_number?: number | null
}

export interface CatalogEditorArtwork {
  id: string
  library_id: string
  target_type:
    | "media_item"
    | "series"
    | "season"
    | "episode"
  target_id: string
  artwork_type:
    | "primary"
    | "backdrop"
    | "banner"
    | "logo"
    | "thumb"
  artwork_type_label: string
  source_name: string
  relative_path: string
  file_name: string
  extension: string
  size_bytes: number
  is_selected: boolean
  is_present: boolean
  content_url: string
  updated_at: string
}

export interface ArtworkRefreshResult {
  created: number
  updated: number
  ignored: number
  error_count: number
  errors: Array<{
    path: string
    error: string
  }>
}

export interface CatalogEditorDetail {
  kind: CatalogEditorKind
  id: string
  media_item_id?: string
  library_id: string
  semantic_key: string | null
  semantic_locked: boolean
  context?: CatalogEditorContext
  metadata: Record<string, unknown>
  field_states: CanonicalFieldState[]
  versions: CatalogEditorVersion[]
  sources: CatalogEditorSource[]
  nfo_files: CatalogEditorNfoFile[]
  artwork: CatalogEditorArtwork[]
  history: MetadataChangeSet[]
}

export interface CatalogMetadataUpdate {
  note?: string
  [key: string]: unknown
}

export interface CatalogVersionUpdate {
  name?: string
  edition?: string
  notes?: string
  note?: string
}
export type NeedsAttentionOrdering =
  | "media_file__file_name"
  | "-media_file__file_name"
  | "media_file__relative_path"
  | "-media_file__relative_path"
  | "status"
  | "-status"
  | "source"
  | "-source"
  | "confidence"
  | "-confidence"
  | "media_file__media_item__title"
  | "-media_file__media_item__title"
  | "media_file__duration_seconds"
  | "-media_file__duration_seconds"
  | "media_file__size_bytes"
  | "-media_file__size_bytes"
  | "updated_at"
  | "-updated_at"

export interface UserSettings {
  display_name: string
  email: string
  is_staff: boolean
  is_superuser: boolean
  default_page_size: PageSize
  needs_attention_unresolved_sort: NeedsAttentionOrdering
  needs_attention_conflict_sort: NeedsAttentionOrdering
  needs_attention_confirmed_sort: NeedsAttentionOrdering
  show_build_information: boolean
  confirm_restart: boolean
  created_at: string
  updated_at: string
}

export interface UserSettingsUpdate {
  display_name?: string
  default_page_size?: PageSize
  needs_attention_unresolved_sort?: NeedsAttentionOrdering
  needs_attention_conflict_sort?: NeedsAttentionOrdering
  needs_attention_confirmed_sort?: NeedsAttentionOrdering
  show_build_information?: boolean
  confirm_restart?: boolean
}

export interface SystemHealth {
  status: "ok"
  version: string
  runtime_started_at: string
}

export interface SystemStatus {
  status: "ok"
  version: SystemVersionInfo
  database: {
    status: "ok" | "error"
    detail: string
  }
  ffprobe: {
    status: "ok" | "missing"
    configured_path: string
    resolved_path: string | null
  }
  restart: {
    supported: boolean
    request_file: string | null
    last_requested_at: string | null
    last_requested_by: string | null
  }
}

export interface RestartRequestResult {
  accepted: boolean
  runtime_started_at: string
}


// Metadata provider matching (read-only search and preview)

export type MetadataMatchKind = "movie" | "series"

export interface MetadataMatchTarget {
  type: MetadataMatchKind
  id: string
  library_id: string
  title: string
  year: number | null
}

export interface MetadataMatchConnection {
  connection_id: string
  connection_name: string
  provider: string
  provider_label: string
  status: string
  available: boolean
  reason: string
  attribution: string
}

export interface MetadataMatchContext {
  target: MetadataMatchTarget
  connections: MetadataMatchConnection[]
  search_defaults: {
    query: string
    year: number | null
    original_title: string
  }
}

export interface MetadataExternalId {
  namespace: string
  value: string
}

export type MetadataMatchTier =
  | "strong"
  | "likely"
  | "possible"
  | "weak"
  | "conflict"

export interface MetadataMatchReason {
  code: string
  label: string
  tone: "positive" | "neutral" | "warning"
}

export interface MetadataMatchCandidate {
  provider: string
  target_type: MetadataMatchKind
  source_id: string
  title: string
  original_title: string
  release_date: string | null
  year: number | null
  overview: string
  artwork_url: string
  external_ids: MetadataExternalId[]
  match: {
    tier: MetadataMatchTier
    reasons: MetadataMatchReason[]
  }
}

export interface MetadataMatchSearchResult {
  target: MetadataMatchTarget
  connection: MetadataMatchConnection
  query: string
  year: number | null
  page: number
  next_page: number | null
  results: MetadataMatchCandidate[]
}

export type MetadataPreviewStatus =
  | "unchanged"
  | "fill"
  | "different"
  | "add"
  | "conflict"
  | "missing"
  | "locked"

export interface MetadataPreviewField {
  field: string
  label: string
  group: "identity" | "descriptive" | "relationships" | "external_ids"
  kind: "text" | "longtext" | "date" | "year" | "rating" | "list" | "external_id"
  current: unknown
  proposed: unknown
  status: MetadataPreviewStatus
  selectable: boolean
  default_selected: boolean
  locked: boolean
  current_source: string | null
  note: string
  additions?: string[]
  result?: string[]
  linked_fields?: string[]
  linked_to?: string
  territory?: string
  namespace?: string
  // True when the proposed rating was estimated from other countries' ratings.
  estimated?: boolean
  estimate?: RatingEstimate | null
}

export interface RatingEstimate {
  value: string
  age: number
  basis: { territory: string; rating: string; age: number }[]
}

export interface MetadataPreviewArtwork {
  url: string
  kind: "poster" | "backdrop" | "logo" | "banner" | "thumbnail" | "other"
  width: number | null
  height: number | null
  language: string | null
  thumbnail_url: string
}

export type ArtworkTypeKey = "primary" | "backdrop" | "logo" | "banner" | "thumb"

export interface ArtworkSource {
  connection_id: string
  connection_name: string
  provider: string
  provider_label: string
  // "details": comes with a matched title; "ids": looked up by TMDB/IMDb/TVDB ID.
  mode: "details" | "ids"
  id_namespaces: string[]
  attribution: string
}

export interface ArtworkChoice extends MetadataPreviewArtwork {
  artwork_type: ArtworkTypeKey
  file_name: string
}

export interface ArtworkChoices {
  target: MetadataMatchTarget
  sources: ArtworkSource[]
  connection: ArtworkSource | null
  writable: boolean
  root_error: string | null
  folder: string | null
  folder_error: string | null
  current: Record<ArtworkTypeKey, CatalogEditorArtwork | null>
  items: ArtworkChoice[]
}

export interface ArtworkSaveResult {
  replayed: boolean
  artwork_type: ArtworkTypeKey
  path: string
  backups: { from: string; to: string }[]
  artwork: CatalogEditorArtwork | null
  change_set_id: string
}

export interface MetadataMatchPreview {
  target: MetadataMatchTarget
  connection: MetadataMatchConnection
  source_id: string
  territory: string
  provider_metadata: {
    title: string
    original_title: string
    year: number | null
    overview: string
    artwork: MetadataPreviewArtwork[]
    [key: string]: unknown
  }
  fields: MetadataPreviewField[]
  not_stored: { label: string; value: string; note: string }[]
  summary: Partial<Record<MetadataPreviewStatus, number>>
  target_revision: string
  provider_snapshot: string
}

export interface MetadataMatchApplyRequest {
  connection: string
  source_id: string
  territory: string
  fields: string[]
  target_revision: string
  provider_snapshot: string
  operation_id: string
}

export interface MetadataMatchApplyResult {
  applied: boolean
  replayed: boolean
  change_set: {
    id: string
    source: string
    source_ref: string
    operation_id: string | null
    fields: string[]
    changes: Record<string, { old: unknown; new: unknown }>
    note: string
    created_at: string
  }
  detail: CatalogEditorDetail
}


// Library content-rating coverage and suggestions

export type RatingStatus = "rated" | "missing" | "unrecognized"

// Online-video channels are rated like TV series.
export type RatingKind = MetadataMatchKind | "channel"

export interface RatingKindInfo {
  kind: RatingKind
  label: string
  total: number
  provider_suggestions: boolean
  nfo: boolean
  youtube_hints: boolean
}

export type YouTubeHintStatus = "hint" | "no_signal" | "not_found" | "not_youtube"
export type YouTubeHintAction = "set" | "change" | "unchanged" | "locked"

export interface YouTubeRatingHint {
  id: string
  title: string
  source_id: string
  current: string
  current_source: string | null
  action: YouTubeHintAction | null
  status: YouTubeHintStatus
  rating: string
  reason: string
  note: string
  stats: {
    channel_found?: boolean
    channel_made_for_kids?: boolean | null
    videos_checked?: number
    videos_made_for_kids?: number
    videos_age_restricted?: number
  }
}

export interface YouTubeRatingHints {
  library_id: string
  connection: { connection_id: string; connection_name: string; provider: string; provider_label: string }
  results: YouTubeRatingHint[]
}

export type YouTubeHintApplyOutcome = "applied" | "unchanged" | "locked" | "changed"

export interface YouTubeHintApplyResult {
  library_id: string
  counts: Record<YouTubeHintApplyOutcome, number>
  results: { id: string; title: string; rating: string; result: YouTubeHintApplyOutcome }[]
}

export interface RatingCounts {
  total: number
  rated: number
  missing: number
  unrecognized: number
}

export interface RatingCoverageRow {
  kind: RatingKind
  id: string
  title: string
  year: number | null
  content_rating: string
  status: RatingStatus
  source: string | null
  source_label: string | null
  locked: boolean
}

export interface RatingCoverage {
  library_id: string
  kind: RatingKind
  status: RatingStatus | "all"
  summary: Record<RatingKind, RatingCounts>
  recognized_ratings: { movie: string[]; tv: string[] }
  kinds: RatingKindInfo[]
  page: number
  page_size: number
  total: number
  next_page: number | null
  results: RatingCoverageRow[]
}

export type RatingSuggestionStatus =
  | "suggested"
  | "estimated"
  | "needs_review"
  | "no_rating"
  | "locked"
  | "unchanged"
  | "error"

export interface RatingSuggestion {
  kind: MetadataMatchKind
  id: string
  title: string
  year: number | null
  content_rating: string
  status: RatingSuggestionStatus
  message: string
  candidate?: MetadataMatchCandidate | null
  rating?: string | null
  territory?: string
  estimate?: RatingEstimate | null
  // Which provider this result came from, and which were tried in order.
  provider?: string
  provider_label?: string
  tried?: string[]
  apply?: Omit<MetadataMatchApplyRequest, "operation_id">
}

export interface RatingSuggestions {
  library_id: string
  kind: MetadataMatchKind
  connection: MetadataMatchConnection
  connections?: MetadataMatchConnection[]
  results: RatingSuggestion[]
}


// Importing ratings from indexed NFO files

export type NfoImportAction =
  | "set"
  | "update"
  | "unchanged"
  | "conflict"
  | "locked"
  | "nfo_disagree"
  | "no_rating_in_nfo"
  | "no_nfo"

export interface NfoImportRow {
  kind: MetadataMatchKind
  id: string
  title: string
  current: string
  current_source: string | null
  nfo_rating: string
  nfo_path: string
  action: NfoImportAction
  other_values?: string[]
}

export interface NfoImportPreview {
  library_id: string
  kind: MetadataMatchKind
  total: number
  summary: Record<NfoImportAction, number>
  rows: NfoImportRow[]
  rows_truncated: boolean
  written?: number
}


// Writing catalog ratings into existing NFO files

export type NfoExportAction = "write" | "add" | "unchanged" | "no_nfo" | "unrated"

export interface NfoExportRow {
  kind: MetadataMatchKind
  id: string
  title: string
  rating: string
  action: NfoExportAction
  nfo_path: string
  nfo_rating: string
}

export interface NfoExportPreview {
  library_id: string
  kind: MetadataMatchKind
  writable: boolean
  management_mode: ManagementMode
  root_error: string | null
  summary: Record<NfoExportAction, number>
  files_to_write: number
  rows: NfoExportRow[]
  rows_truncated: boolean
}

export interface NfoExportProblem {
  title: string
  nfo_path: string
  rating: string
  previous: string
  result: "changed_on_disk" | "failed"
  message: string
}

export interface NfoExportBatch {
  library_id: string
  kind: MetadataMatchKind
  counts: { written: number; changed_on_disk: number; failed: number }
  problems: NfoExportProblem[]
  next_cursor: string | null
  remaining: number
}


export interface ScanWorkerStatus {
  alive: boolean
  stale_after_seconds: number
  workers: {
    id: string
    hostname: string
    pid: number
    started_at: string
    last_seen_at: string
    current_job: string | null
    current_library: string | null
  }[]
  queued_jobs: number
}
