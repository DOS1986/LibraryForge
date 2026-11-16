import { useEffect, useRef, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import { previewNfoRatingExport, writeNfoRatingBatch } from "@/lib/api"

import type {
  MetadataMatchKind,
  NfoExportAction,
  NfoExportPreview,
  NfoExportProblem,
} from "@/types"


interface NfoRatingExportCardProps {
  libraryId: string
  kind: MetadataMatchKind
}

const ACTION_LABELS: Record<NfoExportAction, string> = {
  write: "Will replace the NFO's rating",
  add: "Will add a rating to the NFO",
  unchanged: "NFO already matches",
  no_nfo: "Rated, but no NFO file",
  unrated: "No rating in LibraryForge",
}

const SUMMARY_ORDER: NfoExportAction[] = ["write", "add", "unchanged", "no_nfo", "unrated"]

const BATCH_SIZE = 100


function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}


export function NfoRatingExportCard({
  libraryId,
  kind,
}: NfoRatingExportCardProps) {
  const [preview, setPreview] = useState<NfoExportPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [writing, setWriting] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const [totals, setTotals] = useState<{ written: number; changed_on_disk: number; failed: number } | null>(null)
  const [problems, setProblems] = useState<NfoExportProblem[]>([])
  const [error, setError] = useState<string | null>(null)
  const runRef = useRef(0)

  useEffect(() => {
    runRef.current += 1
    setPreview(null)
    setConfirming(false)
    setWriting(false)
    setProgress(null)
    setTotals(null)
    setProblems([])
    setError(null)
  }, [libraryId, kind])

  async function check() {
    setLoading(true)
    setError(null)
    setConfirming(false)

    try {
      setPreview(await previewNfoRatingExport(libraryId, kind))
    } catch (err) {
      setError(errorMessage(err, "Unable to check NFO files."))
    } finally {
      setLoading(false)
    }
  }

  async function write() {
    if (!preview) {
      return
    }

    const run = ++runRef.current
    const sum = { written: 0, changed_on_disk: 0, failed: 0 }
    const found: NfoExportProblem[] = []
    let cursor: string | null = null

    setWriting(true)
    setConfirming(false)
    setError(null)
    setTotals(null)
    setProblems([])
    setProgress({ done: 0, total: preview.files_to_write })

    try {
      do {
        const batch = await writeNfoRatingBatch(libraryId, kind, cursor, BATCH_SIZE)

        if (runRef.current !== run) {
          return
        }

        sum.written += batch.counts.written
        sum.changed_on_disk += batch.counts.changed_on_disk
        sum.failed += batch.counts.failed
        found.push(...batch.problems)
        cursor = batch.next_cursor

        const done = sum.written + sum.changed_on_disk + sum.failed
        setProgress({ done, total: done + batch.remaining })
      } while (cursor)

      setTotals({ ...sum })
      setProblems(found)
      setPreview(await previewNfoRatingExport(libraryId, kind))
    } catch (err) {
      if (runRef.current === run) {
        setTotals({ ...sum })
        setProblems(found)
        setError(errorMessage(err, "Writing stopped because of an error."))
      }
    } finally {
      if (runRef.current === run) {
        setWriting(false)
        setProgress(null)
      }
    }
  }

  function stop() {
    runRef.current += 1
    setWriting(false)
    setProgress(null)
    void check()
  }

  const noun = kind === "movie" ? "movies" : "TV series"

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Write ratings to NFO files</CardTitle>
        <CardDescription>
          Puts each {kind === "movie" ? "movie" : "series"}&apos;s LibraryForge rating into its existing NFO file
          (&lt;mpaa&gt;), where media servers such as Jellyfin read it for parental controls. Only the rating changes;
          the rest of each file is left as it is. New NFO files aren&apos;t created, and files changed since the last
          scan are skipped.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 text-sm">
        <Button variant="outline" disabled={loading || writing} onClick={() => void check()}>
          {loading ? "Checking NFO files..." : preview ? "Check again" : "Check NFO files"}
        </Button>

        {error && <p className="text-destructive" role="alert">{error}</p>}

        {preview && !preview.writable && (
          <div className="rounded-lg border border-warning/40 bg-warning/10 p-3" role="note">
            This library is <span className="font-medium">Read Only</span>, so LibraryForge won&apos;t change its files.
            To write ratings into its NFO files, change its management mode to{" "}
            <span className="font-medium">Sidecar Only</span> in the library&apos;s Settings. Sidecar Only never
            touches video files.
          </div>
        )}

        {preview?.root_error && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/8 p-3" role="alert">
            {preview.root_error}
          </div>
        )}

        {preview && (
          <div className="grid gap-2 sm:grid-cols-5">
            {SUMMARY_ORDER.map(action => (
              <div key={action} className="rounded-lg border bg-muted/30 px-3 py-2.5">
                <div className="text-xs text-muted-foreground">{ACTION_LABELS[action]}</div>
                <div className="mt-0.5 text-xl font-semibold tabular-nums">{preview.summary[action]}</div>
              </div>
            ))}
          </div>
        )}

        {writing && (
          <div className="flex flex-wrap items-center gap-2" role="status">
            <span>
              Writing NFO files... {progress ? `${progress.done} of ${progress.total}` : ""}
            </span>
            <Button variant="outline" size="sm" onClick={stop}>
              Stop
            </Button>
          </div>
        )}

        {preview && preview.writable && !preview.root_error && preview.files_to_write > 0 && !writing && !confirming && (
          <Button onClick={() => setConfirming(true)}>
            Write ratings to {preview.files_to_write} NFO file{preview.files_to_write === 1 ? "" : "s"}
          </Button>
        )}

        {confirming && preview && (
          <div className="space-y-2 rounded-lg border bg-muted/40 p-3">
            <p>
              Update the rating in {preview.files_to_write} NFO file{preview.files_to_write === 1 ? "" : "s"} for
              these {noun}? Only the &lt;mpaa&gt; value changes. Afterwards, refresh the library&apos;s metadata in your
              media server so it reads the new ratings.
            </p>
            <div className="flex gap-2">
              <Button onClick={() => void write()}>Confirm and write</Button>
              <Button variant="outline" onClick={() => setConfirming(false)}>Cancel</Button>
            </div>
          </div>
        )}

        {totals && (
          <div className="space-y-2" role="status">
            <p className="font-medium">
              Wrote {totals.written} NFO file{totals.written === 1 ? "" : "s"}.
              {totals.changed_on_disk > 0 && ` ${totals.changed_on_disk} skipped because they changed on disk (rescan the library, then try again).`}
              {totals.failed > 0 && ` ${totals.failed} couldn't be written.`}
            </p>
            {problems.length > 0 && (
              <ul className="space-y-1">
                {problems.slice(0, 100).map(problem => (
                  <li key={problem.nfo_path} className="text-xs">
                    <span className="font-medium">{problem.title}</span>{" "}
                    <span className="text-muted-foreground">({problem.nfo_path})</span>: {problem.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {preview && !totals && preview.rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1 pr-3">Title</th>
                  <th className="py-1 pr-3">NFO now</th>
                  <th className="py-1 pr-3">Will be</th>
                  <th className="py-1">Change</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map(row => (
                  <tr key={`${row.id}:${row.nfo_path}`} className="border-t align-top">
                    <td className="py-1 pr-3">
                      <div className="font-medium">{row.title}</div>
                      <div className="text-xs text-muted-foreground">{row.nfo_path}</div>
                    </td>
                    <td className="py-1 pr-3">{row.nfo_rating || "—"}</td>
                    <td className="py-1 pr-3 font-medium">{row.rating}</td>
                    <td className="py-1">
                      <Badge variant="secondary">{ACTION_LABELS[row.action]}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {preview.rows_truncated && (
              <p className="mt-2 text-xs text-muted-foreground">Showing the first {preview.rows.length}.</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
