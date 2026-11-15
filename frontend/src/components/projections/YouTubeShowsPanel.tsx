import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

import { JellyfinRefreshCard } from "@/components/jellyfin/JellyfinPanels"

import {
  createYouTubeShows,
  getYouTubeShows,
  getYouTubeShowsPlan,
  syncYouTubeShows,
} from "@/lib/api"

import type {
  Projection,
  ShowsAction,
  ShowsPlan,
  ShowsProblem,
  ShowsResult,
} from "@/types"


const ACTION_LABELS: Record<ShowsAction, string> = {
  create: "To add",
  update: "To update",
  relink: "To relink",
  replace: "To replace",
  delete: "To remove",
  artwork: "Artwork to fetch",
}

const ACTION_ORDER: ShowsAction[] = ["create", "update", "relink", "replace", "delete", "artwork"]

const KIND_LABELS: Record<string, string> = {
  video: "Video",
  episode_nfo: "Episode NFO",
  thumb: "Thumbnail",
  show_nfo: "Show NFO",
  poster: "Poster",
  fanart: "Fanart",
  artwork: "Channel artwork",
}

const BATCH_SIZE = 25

const SELECT_CLASS = "h-9 rounded-md border bg-background px-2 text-sm"


function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}


function suggestedDestination(libraryPath: string) {
  // Next to the library folder: same share and volume, so hardlinks work.
  const separator = libraryPath.includes("\\") ? "\\" : "/"
  const trimmed = libraryPath.replace(/[\\/]+$/, "")
  const parent = trimmed.slice(0, Math.max(trimmed.lastIndexOf(separator), 0))
  return parent ? `${parent}${separator}YouTube Shows` : ""
}


export function YouTubeShowsPanel({
  libraryId,
  libraryPath,
}: {
  libraryId: string
  libraryPath: string
}) {
  const [projections, setProjections] = useState<Projection[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [destination, setDestination] = useState(() => suggestedDestination(libraryPath))
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const [channel, setChannel] = useState("")
  const [plan, setPlan] = useState<ShowsPlan | null>(null)
  const [checking, setChecking] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const [totals, setTotals] = useState<Record<ShowsResult, number> | null>(null)
  const [problems, setProblems] = useState<ShowsProblem[]>([])
  const [error, setError] = useState<string | null>(null)
  const runRef = useRef(0)

  const loadProjections = useCallback(async () => {
    const items = await getYouTubeShows(libraryId)
    setProjections(items)
    setSelectedId(current => (items.some(item => item.id === current) ? current : items[0]?.id ?? ""))
  }, [libraryId])

  useEffect(() => {
    void loadProjections().catch(err => setError(errorMessage(err, "Unable to load Jellyfin folders.")))
  }, [loadProjections])

  const check = useCallback(async (projectionId: string, channelId: string) => {
    if (!projectionId) {
      return
    }

    setChecking(true)
    setError(null)

    try {
      setPlan(await getYouTubeShowsPlan(projectionId, channelId))
    } catch (err) {
      setError(errorMessage(err, "Unable to check the Jellyfin folder."))
    } finally {
      setChecking(false)
    }
  }, [])

  useEffect(() => {
    runRef.current += 1
    setSyncing(false)
    setProgress(null)
    setTotals(null)
    setProblems([])
    setPlan(null)
    void check(selectedId, channel)
  }, [selectedId, channel, check])

  async function create(event: FormEvent) {
    event.preventDefault()
    setCreating(true)
    setCreateError(null)

    try {
      const created = await createYouTubeShows(libraryId, destination.trim())
      await loadProjections()
      setSelectedId(created.id)
    } catch (err) {
      setCreateError(errorMessage(err, "Unable to set up the Jellyfin folder."))
    } finally {
      setCreating(false)
    }
  }

  async function sync() {
    if (!plan || !selectedId) {
      return
    }

    const run = ++runRef.current
    const sum = Object.fromEntries(
      ["created", "updated", "relinked", "deleted", "artwork", "adopted", "kept", "conflict", "failed"].map(key => [key, 0]),
    ) as Record<ShowsResult, number>
    const found: ShowsProblem[] = []
    let cursor: string | null = null
    let done = 0

    setSyncing(true)
    setError(null)
    setTotals(null)
    setProblems([])
    setProgress({ done: 0, total: plan.pending })

    try {
      do {
        const batch = await syncYouTubeShows(selectedId, { cursor, batch: BATCH_SIZE, channel: channel || null })

        if (runRef.current !== run) {
          return
        }

        for (const [key, value] of Object.entries(batch.counts)) {
          sum[key as ShowsResult] += value
          done += value
        }
        found.push(...batch.problems)
        cursor = batch.next_cursor
        setProgress({ done, total: done + batch.remaining })

        if (batch.error) {
          setError(batch.error)
          break
        }
      } while (cursor)

      setTotals({ ...sum })
      setProblems(found)
      setPlan(await getYouTubeShowsPlan(selectedId, channel))
    } catch (err) {
      if (runRef.current === run) {
        setTotals({ ...sum })
        setProblems(found)
        setError(errorMessage(err, "The sync stopped because of an error."))
      }
    } finally {
      if (runRef.current === run) {
        setSyncing(false)
        setProgress(null)
      }
    }
  }

  function stop() {
    runRef.current += 1
    setSyncing(false)
    setProgress(null)
    void check(selectedId, channel)
  }

  const selected = projections.find(item => item.id === selectedId)
  const blocked = plan?.source_error || plan?.destination_error

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Jellyfin folder: channels as TV shows</CardTitle>
          <CardDescription>
            Builds a separate folder in the layout Jellyfin expects: one show per channel with a tvshow.nfo, poster,
            and fanart, a season per upload year, and each video renamed with its own episode NFO and thumbnail.
            Videos are hardlinked, so they use no extra disk space and TubeArchivist&apos;s folder is never changed.
            Ratings from the Ratings tab are written into every NFO.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4 text-sm">
          {projections.length > 1 && (
            <label className="flex flex-wrap items-center gap-2">
              Folder
              <select className={SELECT_CLASS} value={selectedId} onChange={event => setSelectedId(event.target.value)}>
                {projections.map(item => (
                  <option key={item.id} value={item.id}>{item.destination_path}</option>
                ))}
              </select>
            </label>
          )}

          {!projections.length && (
            <form className="space-y-2" onSubmit={create}>
              <Label htmlFor="youtube-shows-destination">Destination folder</Label>
              <div className="flex flex-wrap gap-2">
                <Input
                  id="youtube-shows-destination"
                  className="min-w-80 flex-1"
                  value={destination}
                  placeholder="\\server\share\YouTube Shows"
                  onChange={event => setDestination(event.target.value)}
                />
                <Button type="submit" disabled={creating || !destination.trim()}>
                  {creating ? "Setting up..." : "Set up folder"}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Choose a folder on the same share and volume as this library, outside it (hardlinks can&apos;t cross
                volumes). It&apos;s created if it doesn&apos;t exist. Nothing is written until you sync.
              </p>
              {createError && <p className="text-destructive" role="alert">{createError}</p>}
            </form>
          )}

          {selected && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{selected.destination_path}</span>
                <Badge variant="secondary">Hardlinks</Badge>
                {plan?.last_run_at && (
                  <span className="text-xs text-muted-foreground">
                    Last synced {new Date(plan.last_run_at).toLocaleString()}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-2">
                  Channels
                  <select
                    className={SELECT_CLASS}
                    value={channel}
                    disabled={syncing}
                    onChange={event => setChannel(event.target.value)}
                  >
                    <option value="">All channels</option>
                    {plan?.channels.map(item => (
                      <option key={item.id} value={item.id}>{item.title}</option>
                    ))}
                  </select>
                </label>
                <Button variant="outline" disabled={checking || syncing} onClick={() => void check(selectedId, channel)}>
                  {checking ? "Checking..." : "Check again"}
                </Button>
              </div>
              {!channel && !plan?.managed_files && (
                <p className="text-xs text-muted-foreground">
                  Tip: sync one channel first and check it in Jellyfin before syncing the rest.
                </p>
              )}

              {error && <p className="text-destructive" role="alert">{error}</p>}

              {blocked && (
                <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3" role="alert">
                  {plan?.source_error && <p>Library folder: {plan.source_error}</p>}
                  {plan?.destination_error && <p>Destination: {plan.destination_error}</p>}
                </div>
              )}

              {plan && (
                <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
                  {ACTION_ORDER.filter(action => action !== "artwork" || plan.artwork_available).map(action => (
                    <div key={action} className="rounded-md border p-2">
                      <div className="text-xs text-muted-foreground">{ACTION_LABELS[action]}</div>
                      <div className="text-lg font-semibold">{plan.summary[action]}</div>
                    </div>
                  ))}
                </div>
              )}

              {plan && !plan.artwork_available && (
                <p className="text-xs text-muted-foreground">
                  No artwork integration is assigned to this library, so shows get no poster or fanart. Add your
                  TubeArchivist or YouTube connection with artwork on the library&apos;s Settings tab.
                </p>
              )}

              {syncing ? (
                <div className="flex flex-wrap items-center gap-2" role="status">
                  <span>Syncing... {progress ? `${progress.done} of ${progress.total}` : ""}</span>
                  <Button variant="outline" size="sm" onClick={stop}>Stop</Button>
                </div>
              ) : (
                plan && !blocked && (
                  <Button disabled={!plan.pending} onClick={() => void sync()}>
                    {plan.pending
                      ? `Sync ${plan.pending} change${plan.pending === 1 ? "" : "s"}${channel ? " for this channel" : ""}`
                      : "Everything is in sync"}
                  </Button>
                )
              )}

              {totals && (
                <div className="space-y-2" role="status">
                  <p className="font-medium">
                    {[
                      totals.created && `${totals.created} added`,
                      totals.updated && `${totals.updated} updated`,
                      totals.relinked && `${totals.relinked} relinked`,
                      totals.deleted && `${totals.deleted} removed`,
                      totals.artwork && `artwork for ${totals.artwork} show${totals.artwork === 1 ? "" : "s"}`,
                      totals.adopted && `${totals.adopted} already in place`,
                    ].filter(Boolean).join(", ") || "Nothing changed"}.
                    {totals.conflict > 0 && ` ${totals.conflict} left alone (see below).`}
                    {totals.failed > 0 && ` ${totals.failed} failed.`}
                  </p>
                  {problems.length > 0 && (
                    <ul className="space-y-1">
                      {problems.slice(0, 100).map(problem => (
                        <li key={`${problem.action}:${problem.path}`} className="text-xs">
                          <span className="font-medium">{problem.path}</span>: {problem.message}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {plan && plan.channels.length > 0 && (
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
                      {plan.channels.map(item => (
                        <tr key={item.id} className="border-t">
                          <td className="py-1 pr-3 font-medium">{item.title}</td>
                          <td className="py-1 pr-3 text-muted-foreground">{item.folder}</td>
                          <td className="py-1 pr-3">
                            {item.rating || <Badge variant="destructive">No rating</Badge>}
                          </td>
                          <td className="py-1 pr-3">{item.videos}</td>
                          <td className="py-1">{item.pending || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {plan && !totals && plan.actions.length > 0 && (
                <details>
                  <summary className="cursor-pointer text-muted-foreground">
                    Show {plan.actions_truncated ? `the first ${plan.actions.length}` : "all"} planned changes
                  </summary>
                  <ul className="mt-2 space-y-1">
                    {plan.actions.map(action => (
                      <li key={`${action.action}:${action.path}`} className="text-xs">
                        <Badge variant="secondary">{ACTION_LABELS[action.action]}</Badge>{" "}
                        <span className="text-muted-foreground">{KIND_LABELS[action.kind] ?? action.kind}</span>{" "}
                        {action.path}
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              <div className="space-y-1 rounded-md bg-muted/50 p-3 text-xs">
                <p className="font-medium">In Jellyfin</p>
                <ol className="list-decimal space-y-1 pl-4">
                  <li>Add {selected.destination_path} as a <span className="font-medium">Shows</span> library.</li>
                  <li>
                    In its metadata settings keep the <span className="font-medium">Nfo</span> reader on and turn off
                    the TubeArchivist plugin and other online metadata downloaders, so the NFOs (and their ratings) are used.
                  </li>
                  <li>Give your child&apos;s account access to this library, not the TubeArchivist one.</li>
                </ol>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {selected && <JellyfinRefreshCard libraryId={libraryId} />}
    </div>
  )
}
