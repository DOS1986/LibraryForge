import { useState } from "react"

import { Link } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

import { getProjectionRunJournal } from "@/lib/api"
import { formatDateTime } from "@/lib/format"
import { RESULT_LABELS, RUN_VARIANT, projectionPath, resultSummary } from "@/lib/projections"

import type { OutputRunRow, Paged, ProjectionRunDetail, RunJournalRow } from "@/types"


type Journal = { rows: Paged<RunJournalRow>; problemsOnly: boolean }


/** A list of runs, each with its journal (every action and its result) on demand. */
export function RunHistory({
  runs,
  showProjection = false,
}: {
  runs: (ProjectionRunDetail | OutputRunRow)[]
  showProjection?: boolean
}) {
  const [journals, setJournals] = useState<Record<string, Journal>>({})
  const [error, setError] = useState<string | null>(null)

  async function load(runId: string, problemsOnly: boolean, page = 1) {
    setError(null)
    try {
      const rows = await getProjectionRunJournal(runId, problemsOnly, page)
      setJournals(current => ({ ...current, [runId]: { rows, problemsOnly } }))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load the run's details.")
    }
  }

  function hide(runId: string) {
    setJournals(current => {
      const next = { ...current }
      delete next[runId]
      return next
    })
  }

  if (!runs.length) {
    return <p className="text-sm text-muted-foreground">No runs yet.</p>
  }

  return (
    <ul className="space-y-2 text-sm">
      {error && <li className="text-destructive" role="alert">{error}</li>}
      {runs.map(run => {
        const journal = journals[run.id]
        const row = run as OutputRunRow
        const problems = run.problems.length > 0 || Boolean(run.error)
        return (
          <li key={run.id} className="space-y-1 border-t pt-2 first:border-t-0 first:pt-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={RUN_VARIANT[run.status] ?? "secondary"}>{run.status_label}</Badge>
              {showProjection && (
                row.library_id ? (
                  <Link className="font-medium underline-offset-4 hover:underline" to={projectionPath(row.library_id, row.in_place)}>
                    {row.library_name}: {run.projection_name}
                  </Link>
                ) : (
                  <span className="font-medium">{run.projection_name} (deleted)</span>
                )
              )}
              {"cleanup" in run && run.cleanup && <Badge variant="outline">Cleanup</Badge>}
              <span className="text-xs text-muted-foreground">{formatDateTime(run.completed_at ?? run.created_at)}</span>
              <span className="text-xs">{resultSummary(run.counts)}</span>
              {run.total > 0 && (
                <Button
                  size="xs"
                  variant="ghost"
                  onClick={() => (journal ? hide(run.id) : void load(run.id, problems))}
                >
                  {journal ? "Hide details" : "Details"}
                </Button>
              )}
            </div>
            {run.error && <p className="text-xs text-destructive">{run.error}</p>}
            {journal && (
              <div className="space-y-2 rounded-lg border bg-muted/30 p-2">
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    className="size-3.5"
                    checked={journal.problemsOnly}
                    onChange={event => void load(run.id, event.target.checked)}
                  />
                  Only notes and problems
                </label>
                {journal.rows.results.length ? (
                  <ul className="space-y-1">
                    {journal.rows.results.map(item => (
                      <li key={item.ordinal} className="text-xs">
                        <Badge variant="secondary">{RESULT_LABELS[item.result] ?? (item.result || item.state)}</Badge>{" "}
                        <span className="break-all">{item.path}</span>
                        {item.message && <span className="text-muted-foreground"> — {item.message}</span>}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    {journal.problemsOnly ? "No notes or problems." : "No actions recorded."}
                  </p>
                )}
                {journal.rows.total > journal.rows.page_size && (
                  <div className="flex items-center gap-2">
                    <Button
                      size="xs"
                      variant="outline"
                      disabled={journal.rows.page <= 1}
                      onClick={() => void load(run.id, journal.problemsOnly, journal.rows.page - 1)}
                    >
                      Previous
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      Page {journal.rows.page} of {Math.ceil(journal.rows.total / journal.rows.page_size)}
                    </span>
                    <Button
                      size="xs"
                      variant="outline"
                      disabled={!journal.rows.next_page}
                      onClick={() => void load(run.id, journal.problemsOnly, journal.rows.page + 1)}
                    >
                      Next
                    </Button>
                  </div>
                )}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
