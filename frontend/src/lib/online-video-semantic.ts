import type {
  OnlineVideoSemanticCandidate,
  SemanticMatch,
} from "@/types"


function asRecord(value: unknown) {
  return (
    value
    && typeof value === "object"
    && !Array.isArray(value)
      ? value as Record<string, unknown>
      : null
  )
}


function stringValue(value: unknown) {
  return typeof value === "string" ? value : ""
}


function stringArray(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : []
}


function readNormalizedCandidate(value: unknown): OnlineVideoSemanticCandidate | null {
  const record = asRecord(value)
  if (!record) {
    return null
  }

  if (
    record.kind === "online_video"
    && typeof record.provider === "string"
    && typeof record.source_id === "string"
  ) {
    return {
      kind: "online_video",
      provider: record.provider,
      source_id: record.source_id,
      title: stringValue(record.title),
      source_url: stringValue(record.source_url),
      upload_date: typeof record.upload_date === "string" ? record.upload_date : null,
      video_kind: stringValue(record.video_kind) || "unknown",
      tags: stringArray(record.tags),
      categories: stringArray(record.categories),
      channel_id: stringValue(record.channel_id),
      channel_title: stringValue(record.channel_title),
      channel_handle: stringValue(record.channel_handle),
      channel_url: stringValue(record.channel_url),
      channel_description: stringValue(record.channel_description),
      confidence: typeof record.confidence === "number" ? record.confidence : 1,
    }
  }

  const video = asRecord(record.video)
  if (!video) {
    return null
  }

  const provider = stringValue(record.provider)
  const sourceId = stringValue(video.id)
  if (!provider || !sourceId) {
    return null
  }

  const channel = asRecord(record.channel) ?? {}

  return {
    kind: "online_video",
    provider,
    source_id: sourceId,
    title: stringValue(video.title),
    source_url: stringValue(video.url),
    upload_date: typeof video.upload_date === "string" ? video.upload_date : null,
    video_kind: stringValue(video.kind) || "unknown",
    tags: stringArray(video.tags),
    categories: stringArray(video.categories),
    channel_id: stringValue(channel.id),
    channel_title: stringValue(channel.title),
    channel_handle: stringValue(channel.handle),
    channel_url: stringValue(channel.url),
    channel_description: stringValue(channel.description),
    confidence: 1,
  }
}


export function getOnlineVideoCandidate(
  match: SemanticMatch,
  source:
    | "tubearchivist"
    | "yt_dlp"
    | "tubearchivist_path"
    | "suggested",
) {
  if (source === "suggested") {
    return (
      readNormalizedCandidate(match.candidate_data.selected)
      ?? readNormalizedCandidate(match.candidate_data.candidate)
      ?? readNormalizedCandidate(match.candidate_data)
    )
  }

  const sources = asRecord(match.candidate_data.sources)
  return readNormalizedCandidate(sources?.[source])
}
