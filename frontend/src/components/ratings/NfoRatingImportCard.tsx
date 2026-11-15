import { useEffect, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import { applyNfoRatingImport, previewNfoRatingImport } from "@/lib/api"

import type {
  MetadataMatchKind,
  NfoImportAction,
  NfoImportPreview,
} from "@/types"


interface NfoRatingImportCardProps {
  libraryId: string
  kind: MetadataMatchKind
  onImported: () => void
}

const ACTION_LABELS: Record<NfoImportAction, string> = {
  set: "Will fill an empty rating",
  update: "Will follow a changed NFO",
  unchanged: "Already matches",
  conflict: "Different rating kept",
  locked: "Locked rating kept",
  nfo_disagree: "NFO files disagree",
  no_rating_in_nfo: "NFO has no rating",
  no_nfo: "No NFO file",
}

const SUMMARY_ORDER: NfoImportAction[] = [
  "set",
  "update",
  "unchanged",
  "conflict",
  "locked",
  "nfo_disagree",
  "no_rating_in_nfo",
  "no_nfo",
]


function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}


export function NfoRatingImportCard({
  libraryId,
  kind,
  onImported,
}: NfoRatingImportCardProps) {
  const [preview, setPreview] = useState<NfoImportPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [written, setWritten] = useState<number | null>(null)

  useEffect(() => {
    setPreview(null)
    setConfirming(false)
    setError(null)
    setWritten(null)
  }, [libraryId, kind])

  async function check() {
    setLoading(true)
    setError(null)
    setWritten(null)
    setConfirming(false)

    try {
      setPreview(await previewNfoRatingImport(libraryId, kind))
    } catch (err) {
      setError(errorMessage(err, "Unable to check NFO files."))
    } finally {
      setLoading(false)
    }
  }

  async function apply() {
    setApplying(true)
    setError(null)

    try {
      const result = await applyNfoRatingImport(libraryId, kind)

      setPreview(result)
      setWritten(result.written ?? 0)
      setConfirming(false)
      onImported()
    } catch (err) {
      setError(errorMessage(err, "Unable to import ratings."))
    } finally {
      setApplying(false)
    }
  }

  const toWrite = preview ? preview.summary.set + preview.summary.update : 0
  const noun = kind === "movie" ? "movie" : "series"

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Import ratings from NFO files</CardTitle>
        <CardDescription>
          Reads the rating (&lt;mpaa&gt;) from the NFO files LibraryForge has already indexed for this library. It
          only fills empty ratings (or follows an NFO that changed since a previous import), and never replaces a
          rating you set by hand or applied from a provider. No files are changed, so this works with read-only
          libraries.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" disabled={loading || applying} onClick={() => void check()}>
            {loading ? "Checking NFO files..." : preview ? "Check again" : "Check NFO files"}
          </Button>
        </div>

        {error && <p className="text-destructive" role="alert">{error}</p>}

        {written !== null && (
          <p className="font-medium" role="status">
            Imported {written} rating{written === 1 ? "" : "s"} from NFO files. They appear in each item&apos;s History
            with the NFO as their source.
          </p>
        )}

        {preview && (
          <>
            <div className="grid gap-2 sm:grid-cols-4">
              {SUMMARY_ORDER.map(action => (
                <div key={action} className="rounded-md border p-2">
                  <div className="text-xs text-muted-foreground">{ACTION_LABELS[action]}</div>
                  <div className="text-lg font-semibold">{preview.summary[action]}</div>
                </div>
              ))}
            </div>

            {toWrite > 0 && !confirming && (
              <Button disabled={applying} onClick={() => setConfirming(true)}>
                Import {toWrite} rating{toWrite === 1 ? "" : "s"}
              </Button>
            )}

            {confirming && (
              <div className="space-y-2 rounded-md bg-muted/50 p-3">
                <p>
                  Set the rating on {toWrite} {noun}
                  {toWrite === 1 || kind === "series" ? "" : "s"} from their NFO files? Items with a different,
                  locked, or disputed rating are left as they are.
                </p>
                <div className="flex gap-2">
                  <Button disabled={applying} onClick={() => void apply()}>
                    {applying ? "Importing..." : "Confirm import"}
                  </Button>
                  <Button variant="outline" disabled={applying} onClick={() => setConfirming(false)}>
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {preview.rows.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="py-1 pr-3">Title</th>
                      <th className="py-1 pr-3">In LibraryForge</th>
                      <th className="py-1 pr-3">In NFO</th>
                      <th className="py-1">Outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map(row => (
                      <tr key={row.id} className="border-t align-top">
                        <td className="py-1 pr-3">
                          <div className="font-medium">{row.title}</div>
                          <div className="text-xs text-muted-foreground">{row.nfo_path}</div>
                        </td>
                        <td className="py-1 pr-3">{row.current || "—"}</td>
                        <td className="py-1 pr-3">
                          {row.other_values ? row.other_values.join(" / ") : row.nfo_rating || "—"}
                        </td>
                        <td className="py-1">
                          <Badge variant={row.action === "conflict" || row.action === "nfo_disagree" ? "destructive" : "secondary"}>
                            {ACTION_LABELS[row.action]}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {preview.rows_truncated && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Showing the first {preview.rows.length}. Conflicts and disagreements are listed first.
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
