import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"

import { JellyfinRefreshCard } from "@/components/jellyfin/JellyfinPanels"

import {
  buildProjectionPlan,
  cancelProjectionRun,
  createLibraryProjection,
  deleteProjection,
  getProjectionPlanActions,
  getProjectionRun,
  getProjectionRunJournal,
  getProjectionRuns,
  getLibraryProjections,
  getOutputProfiles,
  requestProjectionRun,
  updateProjection,
} from "@/lib/api"
import { formatDateTime } from "@/lib/format"
import { newOperationId } from "@/lib/ids"

import type {
  OutputProfile,
  Paged,
  PlanActionKind,
  PlanActionRow,
  Projection,
  ProjectionPlanDetail,
  ProjectionRunDetail,
  ProjectionRunsSummary,
  RunJournalRow,
} from "@/types"


const ACTION_LABELS: Record<PlanActionKind, string> = {
  create: "To add",
  update: "To update",
  relink: "To relink",
  replace: "To replace",
  delete: "To remove",
  artwork: "Artwork to fetch",
  retain: "Kept (source gone)",
}

const ACTION_ORDER: PlanActionKind[] = ["create", "update", "relink", "replace", "delete", "artwork", "retain"]

const RESULT_LABELS: Record<string, string> = {
  created: "added",
  updated: "updated",
  relinked: "relinked",
  deleted: "removed",
  artwork: "artwork fetched",
  adopted: "recovered",
  kept: "left in place",
  conflict: "left alone",
  failed: "failed",
}

const RUN_VARIANT: Record<string, "success" | "warning" | "destructive" | "default" | "secondary"> = {
  succeeded: "success",
  completed_with_errors: "warning",
  failed: "destructive",
  interrupted: "warning",
  cancelled: "secondary",
  queued: "secondary",
  running: "default",
}

const KIND_LABELS: Record<string, string> = {
  movie_nfo: "Movie NFO",
  art: "Artwork",
  video: "Video",
  episode_nfo: "Episode NFO",
  thumb: "Thumbnail",
  show_nfo: "Show NFO",
  poster: "Poster",
  fanart: "Fanart",
  artwork: "Channel artwork",
}

const SELECT_CLASS = "h-9 rounded-lg border bg-card px-2 text-sm shadow-xs"


function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}


type Layout = "movies" | "tv" | "youtube_shows"

const LAYOUT_COPY: Record<Layout, { title: string; description: string; folder: string; scope: string; server: string }> = {
  youtube_shows: {
    title: "channels as TV shows",
    description:
      "One show per channel with tvshow.nfo, poster, and fanart, a season per upload year, and each video renamed with its own NFO and thumbnail. TubeArchivist's folder is never changed.",
    folder: "YouTube Shows",
    scope: "Channels",
    server: "Shows",
  },
  movies: {
    title: "movies",
    description:
      "Each movie in its own Title (Year) folder with a renamed copy or link of its main version, a movie NFO, and its selected artwork. Your library's folders are never changed.",
    folder: "{server} Movies",
    scope: "",
    server: "Movies",
  },
  tv: {
    title: "TV shows",
    description:
      "Each show in a Show (Year) folder with tvshow.nfo and artwork, Season 01 folders with season art, and every episode renamed Show S01E02 - Title with its own NFO and thumbnail. Your library's folders are never changed.",
    folder: "{server} TV",
    scope: "Shows",
    server: "Shows",
  },
}


type Target = OutputProfile["target"]

const SERVERS: { value: Target; label: string }[] = [
  { value: "jellyfin", label: "Jellyfin" },
  { value: "emby", label: "Emby" },
  { value: "kodi", label: "Kodi" },
  { value: "generic", label: "Generic" },
]

function serverLabel(target: string) {
  return SERVERS.find(item => item.value === target)?.label ?? "Media server"
}


function layoutFor(contentType: string): Layout | null {
  return contentType === "movies" ? "movies" : contentType === "tv" ? "tv" : contentType === "online_video" ? "youtube_shows" : null
}


function suggestedDestination(libraryPath: string, layout: Layout, target: Target) {
  // Next to the library folder: same share and volume, so hardlinks work.
  const separator = libraryPath.includes("\\") ? "\\" : "/"
  const trimmed = libraryPath.replace(/[\\/]+$/, "")
  const parent = trimmed.slice(0, Math.max(trimmed.lastIndexOf(separator), 0))
  const folder = LAYOUT_COPY[layout].folder.replace("{server}", serverLabel(target))
  return parent ? `${parent}${separator}${folder}` : ""
}


function resultSummary(counts: Record<string, number>) {
  const parts = Object.entries(counts)
    .filter(([, value]) => value > 0)
    .map(([key, value]) => `${value} ${RESULT_LABELS[key] ?? key}`)
  return parts.length ? parts.join(", ") : "Nothing changed"
}


/** A library's projections: set one up, plan changes, apply them, and see history. */
export function ProjectionPanel({
  libraryId,
  libraryPath,
  contentType,
}: {
  libraryId: string
  libraryPath: string
  contentType: string
}) {
  const fixedLayout = layoutFor(contentType)
  const [newLayout, setNewLayout] = useState<Layout>(fixedLayout ?? "movies")
  const [projections, setProjections] = useState<Projection[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [target, setTarget] = useState<Target>("jellyfin")
  const [profiles, setProfiles] = useState<OutputProfile[]>([])
  const [destination, setDestination] = useState(() => suggestedDestination(libraryPath, fixedLayout ?? "movies", "jellyfin"))
  const [linkMode, setLinkMode] = useState<Projection["link_mode"]>("hardlink")
  const [acknowledge, setAcknowledge] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const [channel, setChannel] = useState("")
  const [plan, setPlan] = useState<ProjectionPlanDetail | null>(null)
  const [actions, setActions] = useState<Paged<PlanActionRow> | null>(null)
  const [actionFilter, setActionFilter] = useState("")
  const [building, setBuilding] = useState(false)
  const [run, setRun] = useState<ProjectionRunDetail | null>(null)
  const [history, setHistory] = useState<ProjectionRunsSummary | null>(null)
  const [journal, setJournal] = useState<Record<string, RunJournalRow[]>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const pollRef = useRef<number | null>(null)

  const selected = projections.find(item => item.id === selectedId)

  const loadProjections = useCallback(async () => {
    const items = (await getLibraryProjections(libraryId)).filter(item => item.layout !== "template")
    setProjections(items)
    setSelectedId(current => (items.some(item => item.id === current) ? current : items.find(item => item.enabled)?.id ?? items[0]?.id ?? ""))
  }, [libraryId])

  const loadHistory = useCallback(async (projectionId: string) => {
    const result = await getProjectionRuns(projectionId)
    setHistory(result)
    if (result.active_run) {
      setRun(result.active_run)
    }
  }, [])

  useEffect(() => {
    void loadProjections().catch(err => setError(errorMessage(err, "Unable to load this library's folders.")))
    void getOutputProfiles().then(setProfiles).catch(() => undefined)
  }, [loadProjections])

  useEffect(() => {
    setPlan(null)
    setActions(null)
    setRun(null)
    setHistory(null)
    setJournal({})
    if (selectedId) {
      void loadHistory(selectedId).catch(() => undefined)
    }
  }, [selectedId, loadHistory])

  // Poll an active run until it finishes.
  useEffect(() => {
    if (!run || !["queued", "running"].includes(run.status)) {
      return
    }
    pollRef.current = window.setTimeout(async () => {
      try {
        const next = await getProjectionRun(run.id)
        setRun(next)
        if (!["queued", "running"].includes(next.status) && selectedId) {
          void loadHistory(selectedId)
        }
      } catch {
        // Try again on the next tick.
      }
    }, 2000)
    return () => {
      if (pollRef.current) window.clearTimeout(pollRef.current)
    }
  }, [run, selectedId, loadHistory])

  async function create(event: FormEvent) {
    event.preventDefault()
    setCreating(true)
    setCreateError(null)
    try {
      const created = await createLibraryProjection(libraryId, {
        destination_path: destination.trim(),
        layout: fixedLayout ? undefined : newLayout,
        link_mode: linkMode,
        hardlink_acknowledged: linkMode === "hardlink" && acknowledge,
        target,
      })
      void getOutputProfiles().then(setProfiles).catch(() => undefined)
      await loadProjections()
      setSelectedId(created.id)
    } catch (err) {
      setCreateError(errorMessage(err, "Unable to set up the folder."))
    } finally {
      setCreating(false)
    }
  }

  async function update(values: Parameters<typeof updateProjection>[1]) {
    if (!selected) return
    setBusy(true)
    setError(null)
    try {
      const updated = await updateProjection(selected.id, values)
      setProjections(current => current.map(item => (item.id === updated.id ? updated : item)))
      setPlan(null)
    } catch (err) {
      setError(errorMessage(err, "Unable to save the setting."))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!selected || !window.confirm(`Delete the "${selected.name}" projection? Files already written stay on disk and become unmanaged.`)) {
      return
    }
    try {
      await deleteProjection(selected.id)
      await loadProjections()
    } catch (err) {
      setError(errorMessage(err, "Unable to delete the projection."))
    }
  }

  async function build() {
    if (!selected) return
    setBuilding(true)
    setError(null)
    setRun(null)
    try {
      const result = await buildProjectionPlan(selected.id, channel || undefined)
      setPlan(result)
      setActions(result.actions)
      setActionFilter("")
    } catch (err) {
      setError(errorMessage(err, "Unable to build a plan."))
    } finally {
      setBuilding(false)
    }
  }

  async function loadActions(page: number, filter: string) {
    if (!plan) return
    try {
      setActions(await getProjectionPlanActions(plan.id, page, filter))
      setActionFilter(filter)
    } catch (err) {
      setError(errorMessage(err, "Unable to load the planned changes."))
    }
  }

  async function apply() {
    if (!plan) return
    setBusy(true)
    setError(null)
    try {
      setRun(await requestProjectionRun(plan.id, plan.digest, newOperationId()))
      setPlan(null)
      setActions(null)
    } catch (err) {
      setError(errorMessage(err, "Unable to start the run."))
    } finally {
      setBusy(false)
    }
  }

  async function cancel() {
    if (!run) return
    try {
      setRun(await cancelProjectionRun(run.id))
    } catch (err) {
      setError(errorMessage(err, "Unable to cancel."))
    }
  }

  async function toggleJournal(runId: string) {
    if (journal[runId]) {
      setJournal(current => {
        const next = { ...current }
        delete next[runId]
        return next
      })
      return
    }
    const rows = await getProjectionRunJournal(runId)
    setJournal(current => ({ ...current, [runId]: rows.results }))
  }

  const blocking = plan?.findings.filter(finding => finding.severity === "blocking") ?? []
  const warnings = plan?.findings.filter(finding => finding.severity === "warning") ?? []
  const active = run && ["queued", "running"].includes(run.status)
  const needsAcknowledgement = selected && selected.link_mode === "hardlink" && !selected.hardlink_acknowledged
  const layout: Layout = (selected?.layout as Layout | undefined) ?? fixedLayout ?? newLayout
  const copy = LAYOUT_COPY[layout] ?? LAYOUT_COPY.movies
  const server = selected?.output_target ?? target
  const serverName = serverLabel(server)
  const profileInfo = plan?.overview.profile
  const scopes = layout === "youtube_shows"
    ? (plan?.overview.channels ?? []).map(item => ({ id: item.id, title: item.title }))
    : layout === "tv"
      ? (plan?.overview.series ?? []).map(item => ({ id: item.id, title: item.title }))
      : []

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{serverName} folder: {copy.title}</CardTitle>
          <CardDescription>
            {copy.description} Ratings from the Ratings tab are written into every NFO. Changes are planned for you to
            review, then applied in the background by the scan worker.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-5 text-sm">
          {projections.length > 1 && (
            <label className="flex flex-wrap items-center gap-2">
              Folder
              <select className={SELECT_CLASS} value={selectedId} onChange={event => setSelectedId(event.target.value)}>
                {projections.map(item => (
                  <option key={item.id} value={item.id}>
                    {item.destination_path}{item.enabled ? "" : " (turned off)"}
                  </option>
                ))}
              </select>
            </label>
          )}

          {!projections.length && (
            <form className="space-y-3" onSubmit={create}>
              {!fixedLayout && (
                <label className="block space-y-1">
                  <span className="block text-xs font-medium text-muted-foreground">Layout</span>
                  <select
                    className={SELECT_CLASS}
                    value={newLayout}
                    onChange={event => {
                      const next = event.target.value as Layout
                      setNewLayout(next)
                      setDestination(suggestedDestination(libraryPath, next, target))
                    }}
                  >
                    <option value="movies">Movies</option>
                    <option value="tv">TV shows</option>
                    <option value="youtube_shows">Online video channels as TV shows</option>
                  </select>
                </label>
              )}
              <label className="block space-y-1">
                <span className="block text-xs font-medium text-muted-foreground">Media server</span>
                <select
                  className={SELECT_CLASS}
                  value={target}
                  onChange={event => {
                    const next = event.target.value as Target
                    setTarget(next)
                    setDestination(suggestedDestination(libraryPath, fixedLayout ?? newLayout, next))
                  }}
                >
                  {SERVERS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
                {target !== "jellyfin" && (
                  <span className="block text-xs text-muted-foreground">
                    Built to {serverLabel(target)}&apos;s published conventions; not yet checked on a live server.
                  </span>
                )}
              </label>
              <div className="space-y-2">
                <Label htmlFor="youtube-shows-destination">Destination folder</Label>
                <Input
                  id="youtube-shows-destination"
                  value={destination}
                  placeholder={`\\\\server\\share\\${copy.folder}`}
                  onChange={event => setDestination(event.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  On the same share and volume as this library, outside it, and inside a folder allowed by
                  LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS. It&apos;s created if it doesn&apos;t exist.
                </p>
              </div>
              <label className="block space-y-1">
                <span className="block text-xs font-medium text-muted-foreground">Media files</span>
                <select className={SELECT_CLASS} value={linkMode} onChange={event => setLinkMode(event.target.value as Projection["link_mode"])}>
                  <option value="hardlink">Hardlinks (no extra space; same volume only)</option>
                  <option value="copy">Copies (independent files; uses the space again)</option>
                  <option value="symlink">Symbolic links (where the share supports them)</option>
                </select>
              </label>
              {linkMode === "hardlink" && (
                <label className="flex items-start gap-2">
                  <input type="checkbox" className="mt-0.5 size-4" checked={acknowledge} onChange={event => setAcknowledge(event.target.checked)} />
                  <span>
                    I understand a hardlink is the same file as the original under a second name, so nothing should write
                    into media through this folder.
                  </span>
                </label>
              )}
              <Button type="submit" disabled={creating || !destination.trim()}>
                {creating ? "Setting up..." : "Set up folder"}
              </Button>
              {createError && <p className="text-destructive" role="alert">{createError}</p>}
            </form>
          )}

          {selected && (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium break-all">{selected.destination_path}</span>
                <Badge variant="secondary">{serverName}</Badge>
                <Badge variant="secondary">{selected.link_mode_label}</Badge>
                {!selected.enabled && <Badge variant="outline">Turned off</Badge>}
                {history?.latest_run && (
                  <span className="text-xs text-muted-foreground">
                    Last run {formatDateTime(history.latest_run.completed_at ?? history.latest_run.created_at)}
                  </span>
                )}
                {history && <span className="text-xs text-muted-foreground">{history.managed_files.toLocaleString()} managed files</span>}
              </div>

              {needsAcknowledgement && (
                <div className="space-y-2 rounded-lg border border-warning/40 bg-warning/10 p-3" role="note">
                  <p>
                    This folder hardlinks videos: each one is the same file as the original under a second name, so it uses
                    no extra space. Nothing should write into the videos through this folder (a media server writing NFOs
                    and images beside them is fine).
                  </p>
                  <Button size="sm" disabled={busy} onClick={() => void update({ hardlink_acknowledged: true })}>
                    I understand, use hardlinks
                  </Button>
                </div>
              )}

              {!selected.enabled && (
                <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 p-3">
                  <span>This projection is turned off (it was converted from the retired template engine).</span>
                  <Button size="sm" variant="outline" disabled={busy} onClick={() => void update({ enabled: true })}>Turn on</Button>
                  <Button size="sm" variant="ghost" onClick={() => void remove()}>Delete</Button>
                </div>
              )}

              <div className="flex flex-wrap items-end gap-3">
                <label className="space-y-1">
                  <span className="block text-xs font-medium text-muted-foreground">When a source file is gone</span>
                  <select
                    className={SELECT_CLASS}
                    value={selected.stale_policy}
                    disabled={busy}
                    onChange={event => void update({ stale_policy: event.target.value as Projection["stale_policy"] })}
                  >
                    <option value="remove_owned">Remove its files from this folder</option>
                    <option value="keep">Keep them</option>
                  </select>
                </label>
                {profiles.length > 1 && (
                  <label className="space-y-1">
                    <span className="block text-xs font-medium text-muted-foreground">Media server profile</span>
                    <select
                      className={SELECT_CLASS}
                      value={selected.output_profile}
                      disabled={busy || Boolean(active)}
                      onChange={event => void update({ output_profile: event.target.value })}
                    >
                      {profiles.map(item => (
                        <option key={item.id} value={item.id}>{item.name} ({item.target_label})</option>
                      ))}
                    </select>
                  </label>
                )}
                {copy.scope && (
                  <label className="space-y-1">
                    <span className="block text-xs font-medium text-muted-foreground">{copy.scope}</span>
                    <select className={SELECT_CLASS} value={channel} onChange={event => setChannel(event.target.value)}>
                      <option value="">All {copy.scope.toLowerCase()}</option>
                      {scopes.map(item => (
                        <option key={item.id} value={item.id}>{item.title}</option>
                      ))}
                    </select>
                  </label>
                )}
                <Button disabled={building || Boolean(active)} onClick={() => void build()}>
                  {building ? "Building plan..." : plan ? "Build a new plan" : "Check for changes"}
                </Button>
              </div>

              {error && <p className="text-destructive" role="alert">{error}</p>}

              {active && run && (
                <div className="space-y-2 rounded-lg border p-3" role="status">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">
                      {run.status === "queued" ? "Waiting for the scan worker..." : `Applying changes... ${run.done} of ${run.total}`}
                    </span>
                    <Button size="sm" variant="outline" disabled={run.cancel_requested} onClick={() => void cancel()}>
                      {run.cancel_requested ? "Cancelling..." : "Cancel"}
                    </Button>
                  </div>
                  <Progress value={run.total ? (run.done / run.total) * 100 : 0} />
                  {run.status === "queued" && (
                    <p className="text-xs text-muted-foreground">Runs are applied by the background worker (run_scan_worker). Make sure it&apos;s running.</p>
                  )}
                </div>
              )}

              {run && !active && (
                <div className="space-y-2 rounded-lg border p-3" role="status">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={RUN_VARIANT[run.status] ?? "secondary"}>{run.status_label}</Badge>
                    <span>{resultSummary(run.counts)}.</span>
                  </div>
                  {run.error && <p className="text-destructive">{run.error}</p>}
                  {run.problems.length > 0 && (
                    <ul className="space-y-1">
                      {run.problems.slice(0, 50).map(problem => (
                        <li key={`${problem.action}:${problem.path}`} className="text-xs">
                          <span className="font-medium break-all">{problem.path}</span>: {problem.message}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {plan && (
                <div className="space-y-4">
                  {profileInfo && profileInfo.notes.length > 0 && (
                    <ul className="space-y-1 rounded-lg border bg-muted/40 p-3 text-xs" role="note">
                      {profileInfo.notes.map(note => <li key={note}>{note}</li>)}
                    </ul>
                  )}
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={plan.status === "ready" ? "default" : plan.status === "blocked" ? "destructive" : "secondary"}>
                      Plan {plan.status}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      Built {formatDateTime(plan.created_at)} · expires {formatDateTime(plan.expires_at)}
                    </span>
                  </div>

                  {blocking.map(finding => (
                    <p key={finding.code} className="rounded-lg border border-destructive/40 bg-destructive/8 p-3" role="alert">{finding.message}</p>
                  ))}
                  {warnings.map(finding => (
                    <p key={finding.code} className="rounded-lg border border-warning/40 bg-warning/10 p-3" role="note">{finding.message}</p>
                  ))}

                  {plan.status !== "blocked" && (
                    <div className="grid gap-2 sm:grid-cols-4 lg:grid-cols-7">
                      {ACTION_ORDER.filter(action => action !== "artwork" || plan.overview.artwork_available).map(action => (
                        <button
                          key={action}
                          type="button"
                          onClick={() => void loadActions(1, actionFilter === action ? "" : action)}
                          className={`rounded-lg border bg-muted/30 px-3 py-2.5 text-left ${actionFilter === action ? "ring-2 ring-ring" : ""}`}
                          aria-pressed={actionFilter === action}
                        >
                          <div className="text-xs font-medium text-muted-foreground">{ACTION_LABELS[action]}</div>
                          <div className="mt-0.5 text-xl font-semibold tabular-nums">{plan.counts[action] ?? 0}</div>
                        </button>
                      ))}
                    </div>
                  )}

                  {plan.status === "ready" && (
                    <div className="flex flex-wrap items-center gap-3">
                      <Button disabled={busy || !plan.changes} onClick={() => void apply()}>
                        {plan.changes ? `Apply reviewed plan (${plan.changes} change${plan.changes === 1 ? "" : "s"})` : "Everything is in sync"}
                      </Button>
                      <span className="text-xs text-muted-foreground">
                        Only these changes are made; each file is rechecked first. Owned files that changed outside LibraryForge are left alone.
                      </span>
                    </div>
                  )}

                  {layout === "movies" && plan.overview.movies !== undefined && (
                    <p className="text-muted-foreground">
                      {plan.overview.movies.toLocaleString()} movie{plan.overview.movies === 1 ? "" : "s"} in this folder
                      {plan.overview.skipped ? `, ${plan.overview.skipped} skipped (see notes above)` : ""}.
                    </p>
                  )}

                  {(plan.overview.series?.length ?? 0) > 0 && (
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead className="text-left text-xs text-muted-foreground">
                          <tr>
                            <th className="py-1 pr-3">Show</th>
                            <th className="py-1 pr-3">Folder</th>
                            <th className="py-1 pr-3">Rating</th>
                            <th className="py-1 pr-3">Episodes</th>
                            <th className="py-1">Changes</th>
                          </tr>
                        </thead>
                        <tbody>
                          {plan.overview.series?.map(item => (
                            <tr key={item.id} className="border-t">
                              <td className="py-1 pr-3 font-medium">{item.title}</td>
                              <td className="py-1 pr-3 text-muted-foreground">{item.folder}</td>
                              <td className="py-1 pr-3">{item.rating || <Badge variant="destructive">No rating</Badge>}</td>
                              <td className="py-1 pr-3">{item.episodes}</td>
                              <td className="py-1">{item.pending || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {(plan.overview.channels?.length ?? 0) > 0 && (
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead className="text-left text-xs text-muted-foreground">
                          <tr>
                            <th className="py-1 pr-3">Show</th>
                            <th className="py-1 pr-3">Folder</th>
                            <th className="py-1 pr-3">Rating</th>
                            <th className="py-1 pr-3">Videos</th>
                            <th className="py-1">Changes</th>
                          </tr>
                        </thead>
                        <tbody>
                          {plan.overview.channels?.map(item => (
                            <tr key={item.id} className="border-t">
                              <td className="py-1 pr-3 font-medium">{item.title}</td>
                              <td className="py-1 pr-3 text-muted-foreground">{item.folder}</td>
                              <td className="py-1 pr-3">{item.rating || <Badge variant="destructive">No rating</Badge>}</td>
                              <td className="py-1 pr-3">{item.videos}</td>
                              <td className="py-1">{item.pending || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {actions && actions.total > 0 && (
                    <div className="space-y-2">
                      <div className="text-xs font-medium text-muted-foreground">
                        Planned changes{actionFilter ? `: ${ACTION_LABELS[actionFilter as PlanActionKind]}` : ""} ({actions.total})
                      </div>
                      <ul className="space-y-1">
                        {actions.results.map(row => (
                          <li key={row.ordinal} className="text-xs">
                            <Badge variant="secondary">{ACTION_LABELS[row.action]}</Badge>{" "}
                            <span className="text-muted-foreground">{KIND_LABELS[row.kind] ?? row.kind}</span>{" "}
                            <span className="break-all">{row.path}</span>
                          </li>
                        ))}
                      </ul>
                      <div className="flex items-center gap-2">
                        <Button size="sm" variant="outline" disabled={actions.page <= 1} onClick={() => void loadActions(actions.page - 1, actionFilter)}>Previous</Button>
                        <span className="text-xs text-muted-foreground">Page {actions.page} of {Math.max(1, Math.ceil(actions.total / actions.page_size))}</span>
                        <Button size="sm" variant="outline" disabled={!actions.next_page} onClick={() => void loadActions(actions.page + 1, actionFilter)}>Next</Button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {history && history.results.length > 0 && (
                <details className="rounded-lg border p-3">
                  <summary className="cursor-pointer font-medium">Run history ({history.results.length})</summary>
                  <ul className="mt-3 space-y-2">
                    {history.results.map(item => (
                      <li key={item.id} className="space-y-1 border-t pt-2 first:border-t-0 first:pt-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={RUN_VARIANT[item.status] ?? "secondary"}>{item.status_label}</Badge>
                          <span className="text-xs text-muted-foreground">{formatDateTime(item.completed_at ?? item.created_at)}</span>
                          <span className="text-xs">{resultSummary(item.counts)}</span>
                          {(item.problems.length > 0 || item.error) && (
                            <Button size="xs" variant="ghost" onClick={() => void toggleJournal(item.id)}>
                              {journal[item.id] ? "Hide details" : "Details"}
                            </Button>
                          )}
                        </div>
                        {item.error && <p className="text-xs text-destructive">{item.error}</p>}
                        {journal[item.id] && (
                          <ul className="space-y-1 pl-2">
                            {journal[item.id].map(row => (
                              <li key={row.ordinal} className="text-xs">
                                <span className="font-medium break-all">{row.path}</span>: {row.message || row.result}
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              <div className="space-y-1 rounded-lg border bg-muted/40 p-3 text-xs">
                <p className="font-medium">In {serverName}</p>
                {server === "kodi" ? (
                  <ol className="list-decimal space-y-1 pl-4">
                    <li>
                      Add {selected.destination_path} as a video source and set its content to{" "}
                      <span className="font-medium">{layout === "movies" ? "Movies" : "TV shows"}</span>.
                    </li>
                    <li>
                      Choose the <span className="font-medium">Local information only</span> scraper, so Kodi reads the NFOs
                      and their ratings instead of looking items up online.
                    </li>
                    <li>For logos and landscape art, set Settings &gt; Media &gt; Videos &gt; Artwork level to Maximum.</li>
                  </ol>
                ) : server === "generic" ? (
                  <p>Point your player at {selected.destination_path}. It holds Kodi-style NFOs with poster and fanart images.</p>
                ) : (
                  <ol className="list-decimal space-y-1 pl-4">
                    <li>Add {selected.destination_path} as a <span className="font-medium">{copy.server}</span> library.</li>
                    <li>
                      Keep the <span className="font-medium">Nfo</span> metadata reader on and turn off online metadata downloaders
                      {layout === "youtube_shows" ? " and the TubeArchivist plugin" : ""} for it, so the NFOs and their ratings are used.
                    </li>
                    <li>
                      Give your child&apos;s account access to this library
                      {layout === "youtube_shows" ? ", not the TubeArchivist one" : " instead of the original"}.
                    </li>
                  </ol>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {selected && server === "jellyfin" && <JellyfinRefreshCard libraryId={libraryId} />}
    </div>
  )
}
