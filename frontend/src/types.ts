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
  file_count: number
  duration_seconds: number
  size_bytes: number
}

export interface LibraryBrowserFile {
  entry_type:
    | "media"
    | "nfo"
  id: string
  media_item: string | null
  name: string
  title: string
  relative_path: string
  media_count: number
  nfo_count: number
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
  media_item_id: string
  title: string
  year?: number | null
  series_id?: string
  series_title?: string
  season_id?: string
  season_number?: number
  episode_number?: number
  episode_end_number?: number | null
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
    | "manual"
  lock?: boolean
  notes?: string
  kind?:
    | "movie"
    | "episode"
  title?: string
  year?: number | null
  edition?: string
  series_title?: string
  series_year?: number | null
  season_number?: number | null
  episode_number?: number | null
  episode_end_number?: number | null
  episode_title?: string
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

export interface ScanJob {
  id: string
  library: string
  library_name: string
  status: ScanJobStatus
  status_label: string
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

