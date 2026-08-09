import type {
  SemanticCandidate,
  SemanticMatch,
} from "@/types"


const emptyCandidate:
  SemanticCandidate = {
    kind:
      "unknown",

    title:
      "",

    year:
      null,

    series_title:
      "",

    series_year:
      null,

    season_number:
      null,

    episode_number:
      null,

    episode_end_number:
      null,

    episode_title:
      "",

    edition:
      "",

    source:
      "",

    confidence:
      0,
  }


function recordValue(
  value: unknown,
) {
  if (
    value
    && typeof value
    === "object"
    && !Array.isArray(
      value
    )
  ) {
    return (
      value as Record<
        string,
        unknown
      >
    )
  }

  return null
}


function stringValue(
  value: unknown,
) {
  return (
    typeof value
    === "string"
      ? value
      : ""
  )
}


function numberValue(
  value: unknown,
) {
  return (
    typeof value
    === "number"
    && Number.isFinite(
      value
    )
      ? value
      : null
  )
}


export function readSemanticCandidate(
  value: unknown,
): SemanticCandidate | null {
  const record =
    recordValue(
      value
    )

  if (!record) {
    return null
  }

  const kind =
    stringValue(
      record.kind
    )

  if (
    kind !== "movie"
    && kind !== "episode"
    && kind !== "unknown"
  ) {
    return null
  }

  return {
    ...emptyCandidate,

    kind,

    title:
      stringValue(
        record.title
      ),

    year:
      numberValue(
        record.year
      ),

    series_title:
      stringValue(
        record.series_title
      ),

    series_year:
      numberValue(
        record.series_year
      ),

    season_number:
      numberValue(
        record.season_number
      ),

    episode_number:
      numberValue(
        record.episode_number
      ),

    episode_end_number:
      numberValue(
        record.episode_end_number
      ),

    episode_title:
      stringValue(
        record.episode_title
      ),

    edition:
      stringValue(
        record.edition
      ),

    source:
      stringValue(
        record.source
      ),

    confidence:
      (
        numberValue(
          record.confidence
        )
        ?? 0
      ),
  }
}


export function getConflictCandidate(
  match: SemanticMatch,
  source:
    | "nfo"
    | "filename",
) {
  return readSemanticCandidate(
    match.candidate_data[
      source
    ]
  )
}


export function getSuggestedCandidate(
  match: SemanticMatch,
) {
  const selected =
    readSemanticCandidate(
      match.candidate_data[
        "selected"
      ]
    )

  if (selected) {
    return selected
  }

  return readSemanticCandidate(
    match.candidate_data
  )
}


export function semanticCandidateTitle(
  candidate:
    SemanticCandidate
    | null,
) {
  if (!candidate) {
    return "Unavailable"
  }

  if (
    candidate.kind
    === "movie"
  ) {
    return (
      candidate.title
      || "Untitled Movie"
    )
  }

  if (
    candidate.kind
    === "episode"
  ) {
    const season =
      candidate.season_number
      ?? 0

    const episode =
      candidate.episode_number
      ?? 0

    const code =
      (
        `S${String(
          season
        ).padStart(
          2,
          "0",
        )}`
        + `E${String(
          episode
        ).padStart(
          2,
          "0",
        )}`
      )

    return (
      `${candidate.series_title || "Unknown Series"} ${code}`
    )
  }

  return "Unknown"
}
