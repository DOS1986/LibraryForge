// Shared labels for projection plans and runs.

export const RESULT_LABELS: Record<string, string> = {
  created: "added",
  updated: "updated",
  relinked: "relinked",
  deleted: "removed",
  artwork: "artwork fetched",
  adopted: "recovered",
  kept: "left in place",
  conflict: "left alone",
  replaced: "replaced (previous files kept as backups)",
  failed: "failed",
}

export const RUN_VARIANT: Record<string, "success" | "warning" | "destructive" | "default" | "secondary"> = {
  succeeded: "success",
  completed_with_errors: "warning",
  failed: "destructive",
  interrupted: "warning",
  cancelled: "secondary",
  queued: "secondary",
  running: "default",
}

export const ACTIVE_RUN = ["queued", "running"]


export function resultSummary(counts: Record<string, number>) {
  const parts = Object.entries(counts)
    .filter(([, value]) => value > 0)
    .map(([key, value]) => `${value} ${RESULT_LABELS[key] ?? key}`)
  return parts.length ? parts.join(", ") : "Nothing changed"
}


/** Where a projection is managed: in-place NFO output lives on the library's NFO page. */
export function projectionPath(libraryId: string, inPlace: boolean) {
  return `/libraries/${libraryId}/${inPlace ? "nfo" : "projections"}`
}
