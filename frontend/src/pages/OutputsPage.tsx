import { useCallback, useEffect, useState } from "react"

import { Link } from "react-router-dom"

import { PageHeader, StatTile } from "@/components/app/PageHeader"
import { OutputProfilesCard } from "@/components/projections/OutputProfilesCard"
import { RunHistory } from "@/components/projections/RunHistory"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

import { getOutputsOverview } from "@/lib/api"
import { formatDateTime } from "@/lib/format"
import { ACTIVE_RUN, RUN_VARIANT, projectionPath } from "@/lib/projections"

import type { OutputProjectionRow, OutputsOverview } from "@/types"


type Tone = "success" | "warning" | "destructive" | "default" | "secondary" | "outline"


/** One line on where an output stands, from its newest plan and run. */
function outputState(row: OutputProjectionRow): { label: string; tone: Tone; detail?: string } {
  const run = row.active_run
  if (run) {
    return run.status === "queued"
      ? { label: "Waiting for the worker", tone: "secondary" }
      : { label: `Applying ${run.done} of ${run.total}`, tone: "default" }
  }
  if (!row.enabled) return { label: "Turned off", tone: "outline" }
  const plan = row.latest_plan
  if (row.needs_preview || (!plan && !row.latest_run)) return { label: "Not checked yet", tone: "secondary" }
  if (plan?.status === "blocked") return { label: "Blocked", tone: "destructive", detail: plan.blocking[0] }
  if (plan && plan.status === "ready" && plan.changes > 0) {
    return { label: `${plan.changes.toLocaleString()} change${plan.changes === 1 ? "" : "s"} to review`, tone: "warning" }
  }
  const latest = row.latest_run
  if (latest && ["failed", "interrupted", "completed_with_errors"].includes(latest.status)) {
    return { label: latest.status_label, tone: RUN_VARIANT[latest.status] ?? "warning", detail: latest.error || undefined }
  }
  if (plan && plan.changes === 0 && !plan.cleanup && ["ready", "expired", "applied"].includes(plan.status)) {
    return { label: "In sync at last check", tone: "success" }
  }
  return { label: "Applied", tone: "success" }
}


export function OutputsPage() {
  const [data, setData] = useState<OutputsOverview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await getOutputsOverview())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load outputs.")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // Follow runs that are still going.
  const running = data?.projections.some(row => row.active_run && ACTIVE_RUN.includes(row.active_run.status)) ?? false
  useEffect(() => {
    if (!running) return
    const timer = window.setTimeout(() => void load(), 3000)
    return () => window.clearTimeout(timer)
  }, [running, data, load])

  const projections = data?.projections ?? []
  const toReview = projections.filter(row => outputState(row).tone === "warning" || outputState(row).tone === "destructive").length
  const managed = projections.reduce((total, row) => total + row.managed_files, 0)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Outputs"
        description="Everything LibraryForge writes for your media servers: projection folders built from your libraries, and NFOs and artwork written into libraries themselves. Each one is changed only through a plan you review."
        actions={
          <Button variant="outline" size="sm" disabled={loading} onClick={() => void load()}>
            {loading ? "Refreshing..." : "Refresh"}
          </Button>
        }
      />

      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}

      {data && (
        <div className="grid gap-3 sm:grid-cols-3">
          <StatTile label="Outputs" value={projections.length.toLocaleString()} />
          <StatTile label="Files LibraryForge manages" value={managed.toLocaleString()} />
          <StatTile
            label="Need attention"
            value={toReview.toLocaleString()}
            tone={toReview ? "warning" : "success"}
            hint={toReview ? "Changes to review, or a blocked plan or failed run" : "Nothing waiting"}
          />
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Outputs</CardTitle>
          <CardDescription>
            Open one to check for changes, review the plan, apply it, or run a cleanup review.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm">
          {data && !projections.length && (
            <p className="text-muted-foreground">
              No outputs yet. Set one up from a library&apos;s Projections page (a separate folder for your media server) or its
              NFO page (NFOs and artwork in the library itself).
            </p>
          )}
          {projections.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="py-1.5 pr-3 font-medium">Library</th>
                    <th className="py-1.5 pr-3 font-medium">Output</th>
                    <th className="py-1.5 pr-3 font-medium">Writes to</th>
                    <th className="py-1.5 pr-3 font-medium">State</th>
                    <th className="py-1.5 pr-3 font-medium">Last run</th>
                    <th className="py-1.5 pr-3 text-right font-medium">Files</th>
                    <th className="py-1.5" />
                  </tr>
                </thead>
                <tbody>
                  {projections.map(row => {
                    const state = outputState(row)
                    return (
                      <tr key={row.id} className="border-t align-top">
                        <td className="py-2 pr-3 font-medium">{row.library_name}</td>
                        <td className="py-2 pr-3">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span>{row.in_place ? "NFOs and artwork in the library" : row.layout_label}</span>
                            <Badge variant="secondary">{row.target_label}</Badge>
                            {!row.in_place && <Badge variant="outline">{row.link_mode_label}</Badge>}
                          </div>
                        </td>
                        <td className="max-w-80 py-2 pr-3 break-all text-muted-foreground">
                          {row.in_place ? row.library_path : row.destination_path}
                        </td>
                        <td className="py-2 pr-3">
                          <Badge variant={state.tone}>{state.label}</Badge>
                          {state.detail && <p className="mt-1 max-w-72 text-xs text-muted-foreground">{state.detail}</p>}
                        </td>
                        <td className="py-2 pr-3 text-xs text-muted-foreground">
                          {row.latest_run ? formatDateTime(row.latest_run.completed_at ?? row.latest_run.created_at) : "Never"}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {row.managed_files.toLocaleString()}
                          {row.unverified_files > 0 && (
                            <span className="block text-xs text-warning">{row.unverified_files} unverified</span>
                          )}
                        </td>
                        <td className="py-2 text-right">
                          <Button size="sm" variant="outline" render={<Link to={projectionPath(row.library_id, row.in_place)} />}>
                            Open
                          </Button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent runs</CardTitle>
          <CardDescription>The newest runs across every output. Details list each file a run changed and why.</CardDescription>
        </CardHeader>
        <CardContent>{data && <RunHistory runs={data.recent_runs} showProjection />}</CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Output folders allowed</CardTitle>
          <CardDescription>
            Projection folders must be inside one of these, set with LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS on the LibraryForge
            server (restart it and the worker after changing it). NFO output into a library needs no entry here.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm">
          {data && !data.roots.length && (
            <p className="rounded-lg border border-warning/40 bg-warning/10 p-3" role="note">
              No output folders are allowed yet, so projection folders can&apos;t be set up. Add the folder(s) next to your
              libraries to LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS.
            </p>
          )}
          {data && data.roots.length > 0 && (
            <ul className="divide-y rounded-lg border">
              {data.roots.map(root => (
                <li key={root.path} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2">
                  <span className="font-medium break-all">{root.path}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">
                      {root.projections} folder{root.projections === 1 ? "" : "s"}
                    </span>
                    {root.state === "ready" ? (
                      <Badge variant="success">Reachable</Badge>
                    ) : root.state === "creatable" ? (
                      <Badge variant="secondary" title="The folder above it exists, so the first run creates this one.">
                        Created on first run
                      </Badge>
                    ) : root.state === "not_answering" ? (
                      <Badge variant="warning">Not answering</Badge>
                    ) : (
                      <Badge variant="destructive" title="Neither this folder nor the one above it can be found.">Not found</Badge>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <OutputProfilesCard />
    </div>
  )
}
