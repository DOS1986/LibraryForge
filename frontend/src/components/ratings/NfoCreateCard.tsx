import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

import { createNfoBatch, previewNfoCreate } from "@/lib/api"

import type { NfoCreatePreview } from "@/types"


const BATCH_SIZE = 50


/** Create NFOs, from LibraryForge's metadata, for movies or series that have none. */
export function NfoCreateCard({ libraryId, kind }: { libraryId: string; kind: "movie" | "series" }) {
  const [preview, setPreview] = useState<NfoCreatePreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const [result, setResult] = useState<{ created: number; problems: { title: string; path: string; message: string }[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const runRef = useRef(0)
  const noun = kind === "movie" ? "movie" : "series"
  const plural = kind === "movie" ? "movies" : "series"

  useEffect(() => {
    runRef.current += 1
    setPreview(null)
    setConfirming(false)
    setProgress(null)
    setResult(null)
    setError(null)
  }, [libraryId, kind])

  async function check() {
    setLoading(true)
    setError(null)
    setConfirming(false)
    try {
      setPreview(await previewNfoCreate(libraryId, kind))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to check for missing NFOs.")
    } finally {
      setLoading(false)
    }
  }

  async function create() {
    if (!preview) {
      return
    }
    const run = ++runRef.current
    const problems: { title: string; path: string; message: string }[] = []
    let created = 0
    let cursor: string | null = null
    setConfirming(false)
    setResult(null)
    setError(null)
    setProgress({ done: 0, total: preview.ready })
    try {
      do {
        const batch = await createNfoBatch(libraryId, kind, cursor, BATCH_SIZE)
        if (runRef.current !== run) {
          return
        }
        created += batch.created
        problems.push(...batch.problems)
        cursor = batch.next_cursor
        setProgress({ done: created + problems.length, total: created + problems.length + batch.remaining })
      } while (cursor)
      setResult({ created, problems })
      setPreview(await previewNfoCreate(libraryId, kind))
    } catch (err) {
      if (runRef.current === run) {
        setResult({ created, problems })
        setError(err instanceof Error ? err.message : "Creating NFOs stopped because of an error.")
      }
    } finally {
      if (runRef.current === run) {
        setProgress(null)
      }
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create missing NFOs</CardTitle>
        <CardDescription>
          Writes an NFO for every {noun} that doesn&apos;t have one, from LibraryForge&apos;s metadata (title, plot,
          rating, dates, genres, studios), {kind === "movie" ? "beside each video as <file name>.nfo" : "as tvshow.nfo in each series' folder"}.
          Existing NFOs aren&apos;t touched; edit those field by field from an item&apos;s NFO tab.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <Button variant="outline" disabled={loading || Boolean(progress)} onClick={() => void check()}>
          {loading ? "Checking..." : preview ? "Check again" : `Find ${plural} without an NFO`}
        </Button>

        {error && <p className="text-destructive" role="alert">{error}</p>}

        {preview && !preview.writable && (
          <p className="rounded-lg border border-warning/40 bg-warning/10 p-3" role="note">
            This library is Read Only, so LibraryForge won&apos;t create files in it. Switch it to Sidecar Only in Settings first.
          </p>
        )}
        {preview?.root_error && <p className="rounded-lg border border-destructive/40 bg-destructive/8 p-3" role="alert">{preview.root_error}</p>}

        {preview && (
          <p>
            <span className="font-medium">{preview.missing}</span> {preview.missing === 1 ? noun : plural} without an NFO
            {preview.blocked > 0 && <span className="text-muted-foreground"> ({preview.blocked} can&apos;t get one yet; see below)</span>}.
          </p>
        )}

        {progress && (
          <div className="flex flex-wrap items-center gap-2" role="status">
            <span>Creating NFOs... {progress.done} of {progress.total}</span>
            <Button size="sm" variant="outline" onClick={() => { runRef.current += 1; setProgress(null); void check() }}>Stop</Button>
          </div>
        )}

        {preview && preview.writable && !preview.root_error && preview.ready > 0 && !progress && !confirming && (
          <Button onClick={() => setConfirming(true)}>Create {preview.ready} NFO{preview.ready === 1 ? "" : "s"}</Button>
        )}

        {confirming && preview && (
          <div className="space-y-2 rounded-lg border bg-muted/40 p-3">
            <p>Create {preview.ready} new NFO file{preview.ready === 1 ? "" : "s"}? No existing file is changed. Afterwards, refresh the library in your media server.</p>
            <div className="flex gap-2">
              <Button onClick={() => void create()}>Confirm and create</Button>
              <Button variant="outline" onClick={() => setConfirming(false)}>Cancel</Button>
            </div>
          </div>
        )}

        {result && (
          <div className="space-y-1" role="status">
            <p className="font-medium">Created {result.created} NFO{result.created === 1 ? "" : "s"}.{result.problems.length ? ` ${result.problems.length} couldn't be created.` : ""}</p>
            <ul className="space-y-1">
              {result.problems.slice(0, 100).map(problem => (
                <li key={`${problem.title}:${problem.path}`} className="text-xs">
                  <span className="font-medium">{problem.title}</span>: {problem.message}
                </li>
              ))}
            </ul>
          </div>
        )}

        {preview && !result && preview.rows.length > 0 && (
          <details>
            <summary className="cursor-pointer text-muted-foreground">
              Show {preview.rows_truncated ? `the first ${preview.rows.length}` : "all"}
            </summary>
            <ul className="mt-2 space-y-1 text-xs">
              {preview.rows.map(row => (
                <li key={row.id}>
                  <span className="font-medium">{row.title}</span>{" "}
                  <span className="text-muted-foreground">{row.path || row.problem}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </CardContent>
    </Card>
  )
}
