import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

import {
  getMetadataMatchContext,
  previewMetadataMatch,
  searchMetadataMatch,
} from "@/lib/api"

import type {
  MetadataMatchCandidate,
  MetadataMatchContext,
  MetadataMatchKind,
  MetadataMatchPreview,
  MetadataMatchSearchResult,
  MetadataMatchTier,
  MetadataPreviewField,
  MetadataPreviewStatus,
} from "@/types"


interface MetadataMatchPanelProps {
  kind: MetadataMatchKind
  id: string
}


const TIER_LABELS: Record<MetadataMatchTier, string> = {
  strong: "Strong match",
  likely: "Likely match",
  possible: "Possible match",
  weak: "Weak match",
  conflict: "Conflicting IDs",
}

const STATUS_LABELS: Record<MetadataPreviewStatus, string> = {
  fill: "Fills empty field",
  different: "Different",
  add: "Adds entries",
  conflict: "Conflict",
  missing: "Not provided",
  locked: "Locked",
  unchanged: "Same",
}

const GROUP_LABELS: Record<MetadataPreviewField["group"], string> = {
  identity: "Identity",
  descriptive: "Description",
  relationships: "Genres and studios",
  external_ids: "External IDs",
}

const GROUP_ORDER: MetadataPreviewField["group"][] = [
  "identity",
  "descriptive",
  "relationships",
  "external_ids",
]

const SELECT_CLASS =
  "h-9 w-full rounded-md border bg-background px-3 text-sm"


function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}


function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "—"
  }

  if (Array.isArray(value)) {
    return value.length ? value.join(", ") : "—"
  }

  return String(value)
}


function toneClass(tone: string) {
  if (tone === "positive") {
    return "text-emerald-600 dark:text-emerald-400"
  }

  if (tone === "warning") {
    return "text-amber-600 dark:text-amber-400"
  }

  return "text-muted-foreground"
}


function CandidateButton({
  candidate,
  onSelect,
}: {
  candidate: MetadataMatchCandidate
  onSelect: () => void
}) {
  const [imageFailed, setImageFailed] = useState(false)

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className="
          flex w-full gap-3 rounded-md border p-3 text-left
          hover:bg-muted/50
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring
        "
      >
        <div className="h-24 w-16 shrink-0 overflow-hidden rounded bg-muted">
          {candidate.artwork_url && !imageFailed && (
            <img
              src={candidate.artwork_url}
              alt=""
              loading="lazy"
              referrerPolicy="no-referrer"
              className="h-full w-full object-cover"
              onError={() => setImageFailed(true)}
            />
          )}
        </div>

        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-medium">{candidate.title}</span>
            <span className="text-sm text-muted-foreground">
              {candidate.year ?? "Year unknown"}
            </span>
            <Badge variant={candidate.match.tier === "conflict" ? "destructive" : "secondary"}>
              {TIER_LABELS[candidate.match.tier]}
            </Badge>
          </div>

          {candidate.original_title && (
            <div className="text-xs text-muted-foreground">
              Original title: {candidate.original_title}
            </div>
          )}

          <ul className="flex flex-wrap gap-x-3 text-xs">
            {candidate.match.reasons.map(reason => (
              <li key={reason.code} className={toneClass(reason.tone)}>
                {reason.label}
              </li>
            ))}
          </ul>

          {candidate.overview && (
            <p className="line-clamp-2 text-sm text-muted-foreground">
              {candidate.overview}
            </p>
          )}

          <div className="text-xs text-muted-foreground">
            {candidate.provider.toUpperCase()} {candidate.target_type} · ID {candidate.source_id}
          </div>
        </div>
      </button>
    </li>
  )
}


function PreviewRow({
  row,
  checked,
  onToggle,
}: {
  row: MetadataPreviewField
  checked: boolean
  onToggle: () => void
}) {
  const inputId = `match-field-${row.field}`
  const proposed = row.kind === "list" && row.status === "add"
    ? row.result
    : row.proposed

  return (
    <tr className="border-t align-top">
      <td className="py-2 pr-3">
        <input
          id={inputId}
          type="checkbox"
          className="mt-1 size-4"
          checked={checked}
          disabled={!row.selectable}
          onChange={onToggle}
          aria-describedby={row.note ? `${inputId}-note` : undefined}
        />
      </td>

      <td className="py-2 pr-3">
        <label htmlFor={inputId} className="font-medium">
          {row.label}
        </label>
        <div>
          <Badge variant={row.status === "conflict" ? "destructive" : "secondary"}>
            {STATUS_LABELS[row.status]}
          </Badge>
        </div>
        {row.current_source && (
          <div className="text-xs text-muted-foreground">
            Current source: {row.current_source}
          </div>
        )}
      </td>

      <td className="py-2 pr-3">
        <div className={row.kind === "longtext" ? "max-h-40 overflow-y-auto whitespace-pre-wrap" : ""}>
          {displayValue(row.current)}
        </div>
      </td>

      <td className="py-2">
        <div
          className={[
            row.kind === "longtext" ? "max-h-40 overflow-y-auto whitespace-pre-wrap" : "",
            checked ? "font-medium" : "",
          ].join(" ")}
        >
          {displayValue(proposed)}
        </div>
        {row.note && (
          <div id={`${inputId}-note`} className="mt-1 text-xs text-muted-foreground">
            {row.note}
          </div>
        )}
      </td>
    </tr>
  )
}


export function MetadataMatchPanel({
  kind,
  id,
}: MetadataMatchPanelProps) {
  const [context, setContext] = useState<MetadataMatchContext | null>(null)
  const [contextError, setContextError] = useState<string | null>(null)

  const [connectionId, setConnectionId] = useState("")
  const [query, setQuery] = useState("")
  const [year, setYear] = useState("")

  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [results, setResults] = useState<MetadataMatchSearchResult | null>(null)

  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [preview, setPreview] = useState<MetadataMatchPreview | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false

    setContext(null)
    setContextError(null)
    setResults(null)
    setPreview(null)

    getMetadataMatchContext(kind, id)
      .then(data => {
        if (cancelled) {
          return
        }

        setContext(data)
        setQuery(data.search_defaults.query)
        setYear(data.search_defaults.year ? String(data.search_defaults.year) : "")
        setConnectionId(data.connections.find(item => item.available)?.connection_id ?? "")
      })
      .catch(error => {
        if (!cancelled) {
          setContextError(errorMessage(error, "Unable to load metadata providers."))
        }
      })

    return () => {
      cancelled = true
    }
  }, [kind, id])

  const available = useMemo(
    () => context?.connections.filter(item => item.available) ?? [],
    [context],
  )

  const unavailable = useMemo(
    () => context?.connections.filter(item => !item.available) ?? [],
    [context],
  )

  const activeConnection = available.find(item => item.connection_id === connectionId)

  async function runSearch(page = 1) {
    setSearching(true)
    setSearchError(null)

    try {
      setResults(
        await searchMetadataMatch(kind, id, {
          connection: connectionId,
          query,
          year,
          page,
        }),
      )
    } catch (error) {
      setSearchError(errorMessage(error, "Search failed."))
    } finally {
      setSearching(false)
    }
  }

  function handleSearch(event: FormEvent) {
    event.preventDefault()
    void runSearch(1)
  }

  async function openPreview(candidate: MetadataMatchCandidate) {
    setPreview(null)
    setPreviewError(null)
    setPreviewLoading(true)

    try {
      const data = await previewMetadataMatch(kind, id, {
        connection: connectionId,
        source_id: candidate.source_id,
      })

      setPreview(data)
      setSelected(new Set(data.fields.filter(row => row.default_selected).map(row => row.field)))
    } catch (error) {
      setPreviewError(errorMessage(error, "Unable to load provider details."))
    } finally {
      setPreviewLoading(false)
    }
  }

  function toggle(row: MetadataPreviewField) {
    if (!preview) {
      return
    }

    setSelected(current => {
      const next = new Set(current)

      if (next.has(row.field)) {
        next.delete(row.field)
        return next
      }

      next.add(row.field)

      // Keep year and release date consistent when the date is chosen.
      for (const linked of row.linked_fields ?? []) {
        const linkedRow = preview.fields.find(item => item.field === linked)

        if (linkedRow?.selectable) {
          next.add(linked)
        }
      }

      return next
    })
  }

  function closePreview() {
    setPreview(null)
    setPreviewError(null)
  }

  if (contextError) {
    return <p className="text-sm text-destructive">{contextError}</p>
  }

  if (!context) {
    return <p className="text-sm text-muted-foreground">Loading metadata providers...</p>
  }

  if (!available.length) {
    return (
      <div className="space-y-2 text-sm">
        <p>
          No metadata provider for {kind === "movie" ? "movies" : "TV series"} is assigned to this library.
          Add a TMDB connection under Settings → Integrations, then assign it to this library with
          the metadata capability.
        </p>
        {unavailable.map(item => (
          <p key={item.connection_id} className="text-muted-foreground">
            {item.connection_name}: {item.reason}
          </p>
        ))}
      </div>
    )
  }

  const selectedRows = preview?.fields.filter(row => selected.has(row.field)) ?? []

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">
        Search a metadata provider and compare its details with this {kind === "movie" ? "movie" : "series"}.
        This is review only: nothing in your catalog changes here.
      </p>

      {!preview && (
        <>
          <form onSubmit={handleSearch} className="grid gap-3 sm:grid-cols-[1fr_7rem_auto] sm:items-end">
            {available.length > 1 && (
              <div className="space-y-1 sm:col-span-3">
                <Label htmlFor="match-connection">Provider</Label>
                <select
                  id="match-connection"
                  className={SELECT_CLASS}
                  value={connectionId}
                  onChange={event => setConnectionId(event.target.value)}
                >
                  {available.map(item => (
                    <option key={item.connection_id} value={item.connection_id}>
                      {item.connection_name} ({item.provider_label})
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="space-y-1">
              <Label htmlFor="match-query">Title</Label>
              <Input
                id="match-query"
                value={query}
                maxLength={200}
                onChange={event => setQuery(event.target.value)}
                required
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="match-year">Year</Label>
              <Input
                id="match-year"
                inputMode="numeric"
                value={year}
                maxLength={4}
                onChange={event => setYear(event.target.value.replace(/\D/g, ""))}
              />
            </div>

            <Button type="submit" disabled={searching || !query.trim()}>
              {searching ? "Searching..." : "Search"}
            </Button>
          </form>

          {searchError && (
            <p className="text-sm text-destructive" role="alert">{searchError}</p>
          )}

          {previewError && (
            <p className="text-sm text-destructive" role="alert">{previewError}</p>
          )}

          {previewLoading && (
            <p className="text-sm text-muted-foreground">Loading details...</p>
          )}

          {results && (
            <div className="space-y-3">
              <div className="text-sm text-muted-foreground">
                {results.results.length
                  ? `Page ${results.page}. Choose a result to compare it with this item.`
                  : "No results. Try a different title or remove the year."}
              </div>

              <ul className="space-y-2">
                {results.results.map(candidate => (
                  <CandidateButton
                    key={`${candidate.provider}:${candidate.target_type}:${candidate.source_id}`}
                    candidate={candidate}
                    onSelect={() => void openPreview(candidate)}
                  />
                ))}
              </ul>

              <div className="flex gap-2">
                {results.page > 1 && (
                  <Button variant="outline" disabled={searching} onClick={() => void runSearch(results.page - 1)}>
                    Previous page
                  </Button>
                )}
                {results.next_page && (
                  <Button variant="outline" disabled={searching} onClick={() => void runSearch(results.next_page ?? 1)}>
                    Next page
                  </Button>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {preview && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="font-medium">
                {preview.provider_metadata.title}
                {preview.provider_metadata.year ? ` (${preview.provider_metadata.year})` : ""}
              </div>
              <div className="text-xs text-muted-foreground">
                {preview.connection.provider_label} ID {preview.source_id}
              </div>
            </div>
            <Button variant="outline" onClick={closePreview}>
              Back to results
            </Button>
          </div>

          {GROUP_ORDER.map(group => {
            const rows = preview.fields.filter(row => row.group === group)

            if (!rows.length) {
              return null
            }

            return (
              <section key={group} aria-labelledby={`match-group-${group}`}>
                <h3 id={`match-group-${group}`} className="mb-1 text-sm font-semibold">
                  {GROUP_LABELS[group]}
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left text-xs text-muted-foreground">
                      <tr>
                        <th className="w-8 py-1"><span className="sr-only">Use</span></th>
                        <th className="w-48 py-1">Field</th>
                        <th className="py-1">In your catalog</th>
                        <th className="py-1">From {preview.connection.provider_label}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(row => (
                        <PreviewRow
                          key={row.field}
                          row={row}
                          checked={selected.has(row.field)}
                          onToggle={() => toggle(row)}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )
          })}

          {preview.not_stored.length > 0 && (
            <section className="space-y-1 text-sm">
              <h3 className="font-semibold">Also from {preview.connection.provider_label} (not stored)</h3>
              {preview.not_stored.map(item => (
                <p key={item.label}>
                  <span className="font-medium">{item.label}:</span> {item.value}
                  <span className="text-muted-foreground"> — {item.note}</span>
                </p>
              ))}
            </section>
          )}

          {preview.provider_metadata.artwork.length > 0 && (
            <p className="text-sm text-muted-foreground">
              {preview.provider_metadata.artwork.length} artwork images are available from{" "}
              {preview.connection.provider_label}. Choosing artwork comes in a later step.
            </p>
          )}

          <section className="space-y-2 rounded-md border p-3 text-sm">
            <h3 className="font-semibold">Your choices ({selectedRows.length})</h3>
            {selectedRows.length ? (
              <ul className="list-disc pl-5">
                {selectedRows.map(row => (
                  <li key={row.field}>
                    {row.label}: {displayValue(row.kind === "list" ? row.result : row.proposed)}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground">No fields selected.</p>
            )}
            <p className="text-muted-foreground">
              Review only. LibraryForge hasn't changed anything, and applying these choices isn't available yet.
            </p>
          </section>
        </div>
      )}

      {activeConnection?.attribution && (
        <p className="border-t pt-3 text-xs text-muted-foreground">
          {activeConnection.attribution}
        </p>
      )}
    </div>
  )
}
