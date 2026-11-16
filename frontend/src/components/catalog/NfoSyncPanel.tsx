import { useCallback, useEffect, useMemo, useState } from "react"

import { FilePlus2, FileText } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

import { getItemNfo, writeItemNfo } from "@/lib/api"

import type { NfoComparison, NfoFieldRow, NfoFieldStatus, NfoSyncKind } from "@/types"


const STATUS: Record<NfoFieldStatus, { label: string; variant: "success" | "warning" | "secondary" | "outline" }> = {
  same: { label: "Matches", variant: "success" },
  different: { label: "Differs", variant: "warning" },
  missing: { label: "Not in NFO", variant: "secondary" },
  empty: { label: "Empty", variant: "outline" },
  nfo_only: { label: "Only in NFO (kept)", variant: "outline" },
}

const KINDS: Record<"movie" | "series" | "episode", NfoSyncKind> = { movie: "movies", series: "series", episode: "episodes" }


function show(value: string | string[] | null) {
  if (value === null) {
    return "—"
  }
  const text = Array.isArray(value) ? value.join(", ") : value
  return text || "—"
}


/**
 * LibraryForge's fields beside the item's NFO. Write chosen fields into the
 * NFO (everything else in the file is kept), or create the NFO if it's missing.
 */
export function NfoSyncPanel({
  kind,
  id,
  onWritten,
}: {
  kind: "movie" | "series" | "episode"
  id: string
  onWritten?: () => void | Promise<void>
}) {
  const [data, setData] = useState<NfoComparison | null>(null)
  const [chosen, setChosen] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const apply = useCallback((result: NfoComparison) => {
    setData(result)
    setChosen(new Set(result.fields.filter(row => row.status === "different" || row.status === "missing").map(row => row.tag)))
  }, [])

  useEffect(() => {
    setData(null)
    setMessage(null)
    setError(null)
    getItemNfo(KINDS[kind], id).then(apply).catch(err => setError(err instanceof Error ? err.message : "Unable to compare with the NFO."))
  }, [kind, id, apply])

  const changeable = useMemo(
    () => (data?.fields ?? []).filter(row => row.status === "different" || row.status === "missing"),
    [data],
  )

  async function write() {
    if (!data) {
      return
    }
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await writeItemNfo(KINDS[kind], id, data.nfo.exists ? Array.from(chosen) : undefined)
      apply(result.comparison)
      setMessage(
        result.result === "created"
          ? `Created ${result.path}.`
          : result.result === "updated"
            ? `Updated ${result.written.length} field${result.written.length === 1 ? "" : "s"} in ${result.path}.`
            : "The NFO already matched.",
      )
      await onWritten?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to write the NFO.")
    } finally {
      setBusy(false)
    }
  }

  function toggle(row: NfoFieldRow) {
    setChosen(current => {
      const next = new Set(current)
      if (next.has(row.tag)) {
        next.delete(row.tag)
      } else {
        next.add(row.tag)
      }
      return next
    })
  }

  const blocked = data && (!data.writable || data.root_error || data.problem)

  return (
    <section className="space-y-3 rounded-xl border p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="flex items-center gap-2 font-semibold">
            {data?.nfo.exists ? <FileText className="size-4" /> : <FilePlus2 className="size-4" />}
            LibraryForge and the NFO
          </h3>
          <p className="text-muted-foreground">
            {data?.nfo.exists
              ? "Write LibraryForge's values into the NFO. Only the fields you tick change; every other tag stays as it is."
              : "This item has no NFO yet. Create one with everything LibraryForge knows, beside the video, in the name Jellyfin reads."}
          </p>
          {data?.nfo.path && <p className="break-all font-mono text-xs text-muted-foreground">{data.nfo.path}</p>}
        </div>
      </div>

      {error && <p className="text-destructive" role="alert">{error}</p>}
      {data?.problem && <p className="rounded-lg border border-warning/40 bg-warning/10 p-3" role="note">{data.problem}</p>}
      {data && !data.writable && (
        <p className="rounded-lg border border-warning/40 bg-warning/10 p-3" role="note">
          This library is Read Only, so its NFOs can be compared but not written. Switch it to Sidecar Only in Settings to write them.
        </p>
      )}
      {data?.root_error && <p className="text-destructive" role="alert">{data.root_error}</p>}

      {data && (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                {data.nfo.exists && <th className="w-8 py-1.5 pr-2"><span className="sr-only">Write</span></th>}
                <th className="py-1.5 pr-3">Field</th>
                <th className="py-1.5 pr-3">LibraryForge</th>
                {data.nfo.exists && <th className="py-1.5 pr-3">NFO now</th>}
                <th className="py-1.5">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.fields.map(row => {
                const canWrite = row.status === "different" || row.status === "missing"
                return (
                  <tr key={row.tag} className="border-t align-top">
                    {data.nfo.exists && (
                      <td className="py-1.5 pr-2">
                        <input
                          type="checkbox"
                          className="mt-0.5 size-4"
                          aria-label={`Write ${row.label}`}
                          disabled={!canWrite}
                          checked={canWrite && chosen.has(row.tag)}
                          onChange={() => toggle(row)}
                        />
                      </td>
                    )}
                    <td className="py-1.5 pr-3 font-medium whitespace-nowrap">{row.label}</td>
                    <td className="max-w-xs py-1.5 pr-3 break-words">
                      <span className="line-clamp-3">{show(row.libraryforge)}</span>
                    </td>
                    {data.nfo.exists && (
                      <td className="max-w-xs py-1.5 pr-3 break-words text-muted-foreground">
                        <span className="line-clamp-3">{show(row.nfo)}</span>
                      </td>
                    )}
                    <td className="py-1.5">
                      <Badge variant={STATUS[row.status].variant}>{STATUS[row.status].label}</Badge>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {data && !blocked && (
        <div className="flex flex-wrap items-center gap-2">
          {data.nfo.exists ? (
            <Button disabled={busy || !changeable.length || !chosen.size} onClick={() => void write()}>
              {busy
                ? "Writing..."
                : changeable.length
                  ? `Write ${chosen.size} field${chosen.size === 1 ? "" : "s"} to the NFO`
                  : "The NFO matches LibraryForge"}
            </Button>
          ) : (
            <Button disabled={busy} onClick={() => void write()}>
              {busy ? "Creating..." : "Create NFO"}
            </Button>
          )}
          <span className="text-xs text-muted-foreground">Then refresh the library in Jellyfin to read it.</span>
        </div>
      )}

      {message && <p className="text-success" role="status">{message}</p>}
    </section>
  )
}
