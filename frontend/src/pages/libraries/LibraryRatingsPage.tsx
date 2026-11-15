import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react"

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

import { CatalogItemEditorDialog } from "@/components/catalog/CatalogItemEditorDialog"
import { NfoRatingImportCard } from "@/components/ratings/NfoRatingImportCard"
import { NfoRatingExportCard } from "@/components/ratings/NfoRatingExportCard"

import {
  ApiError,
  applyMetadataMatch,
  getLibraryRatings,
  getRatingSuggestions,
  setLibraryRatings,
} from "@/lib/api"
import { newOperationId } from "@/lib/ids"
import { useLibraryOutlet } from "@/lib/route-context"

import type {
  RatingKind,
  MetadataMatchKind,
  RatingCoverage,
  RatingCoverageRow,
  RatingStatus,
  RatingSuggestion,
} from "@/types"


type StatusFilter = RatingStatus | "all"

interface SuggestionState extends RatingSuggestion {
  operationId: string
  applying?: boolean
  applied?: boolean
  error?: string
}

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "missing", label: "Missing" },
  { value: "unrecognized", label: "Unrecognized" },
  { value: "rated", label: "Rated" },
  { value: "all", label: "All" },
]

const STATUS_LABELS: Record<RatingStatus, string> = {
  rated: "Rated",
  missing: "No rating",
  unrecognized: "Unrecognized",
}

// The server answers at most 10 items per request. A whole page is worked
// through in sequential batches so the metadata provider isn't flooded.
const SUGGESTIONS_PER_REQUEST = 10

const DEFAULT_KIND: Record<string, RatingKind> = {
  movies: "movie",
  tv: "series",
  online_video: "channel",
}

const MOVIE_RATINGS = ["G", "PG", "PG-13", "R", "NC-17"]
const TV_RATINGS = ["TV-Y", "TV-Y7", "TV-Y7-FV", "TV-G", "TV-PG", "TV-14", "TV-MA"]

const PAGE_SIZES = [25, 50, 100, 200] as const
const DEFAULT_PAGE_SIZE = 50
const PAGE_SIZE_KEY = "libraryforge.ratings.pageSize"

const SELECT_CLASS = "h-8 rounded-md border bg-background px-2 text-sm"


function storedPageSize() {
  try {
    const value = Number(window.localStorage.getItem(PAGE_SIZE_KEY))
    return (PAGE_SIZES as readonly number[]).includes(value) ? value : DEFAULT_PAGE_SIZE
  } catch {
    return DEFAULT_PAGE_SIZE
  }
}


function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}


export function LibraryRatingsPage() {
  const { library } = useLibraryOutlet()

  const [kind, setKind] = useState<RatingKind>(
    DEFAULT_KIND[library.content_type] ?? "movie",
  )
  const [status, setStatus] = useState<StatusFilter>("missing")
  const [search, setSearch] = useState("")
  const [appliedSearch, setAppliedSearch] = useState("")
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(storedPageSize)

  const [coverage, setCoverage] = useState<RatingCoverage | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [suggestions, setSuggestions] = useState<Record<string, SuggestionState>>({})
  const [finding, setFinding] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  // Incremented to cancel an in-progress run (Stop, or leaving the page).
  const runRef = useRef(0)
  const [findError, setFindError] = useState<string | null>(null)
  const [attribution, setAttribution] = useState("")

  const [editing, setEditing] = useState<{ kind: MetadataMatchKind; id: string; title: string } | null>(null)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [manualRating, setManualRating] = useState("")
  const [confirmingManual, setConfirmingManual] = useState(false)
  const [savingManual, setSavingManual] = useState(false)
  const [manualMessage, setManualMessage] = useState<string | null>(null)

  const load = useCallback(async (quiet = false) => {
    if (!quiet) {
      setLoading(true)
    }
    setLoadError(null)

    try {
      setCoverage(
        await getLibraryRatings(library.id, {
          kind,
          status,
          search: appliedSearch,
          page,
          page_size: pageSize,
        }),
      )
    } catch (error) {
      setLoadError(errorMessage(error, "Unable to load ratings."))
    } finally {
      setLoading(false)
    }
  }, [library.id, kind, status, appliedSearch, page, pageSize])

  useEffect(() => {
    void load()
  }, [load])

  // A run belongs to the page it started on.
  useEffect(() => {
    runRef.current += 1
    setFinding(false)
    setProgress(null)
  }, [library.id, kind, status, appliedSearch, page, pageSize])

  useEffect(() => {
    setSuggestions({})
    setFindError(null)
  }, [library.id, kind])

  // Selection belongs to the page of rows it was made on.
  useEffect(() => {
    setSelected(new Set())
    setConfirmingManual(false)
  }, [library.id, kind, status, appliedSearch, page, pageSize])

  // Switch to a kind this library actually has (for example a mixed library).
  useEffect(() => {
    if (coverage && coverage.kinds.length && !coverage.kinds.some(item => item.kind === kind)) {
      setKind(coverage.kinds[0].kind)
    }
  }, [coverage, kind])

  function changeKind(next: RatingKind) {
    setKind(next)
    setPage(1)
  }

  function changeStatus(next: StatusFilter) {
    setStatus(next)
    setPage(1)
  }

  function changePageSize(next: number) {
    setPageSize(next)
    setPage(1)

    try {
      window.localStorage.setItem(PAGE_SIZE_KEY, String(next))
    } catch {
      // Storage can be unavailable (private mode); the choice just isn't kept.
    }
  }

  function handleSearch(event: FormEvent) {
    event.preventDefault()
    setAppliedSearch(search.trim())
    setPage(1)
  }

  const rows = coverage?.results ?? []
  const pending = rows.filter(row => row.status !== "rated" && !suggestions[row.id])

  async function findRatings(ids: string[]) {
    if (!ids.length) {
      return
    }

    const run = ++runRef.current

    setFinding(true)
    setFindError(null)
    setProgress({ done: 0, total: ids.length })

    try {
      for (let start = 0; start < ids.length; start += SUGGESTIONS_PER_REQUEST) {
        const batch = ids.slice(start, start + SUGGESTIONS_PER_REQUEST)
        const data = await getRatingSuggestions(library.id, kind as MetadataMatchKind, batch)

        if (runRef.current !== run) {
          return
        }

        setAttribution(data.connection.attribution)
        setSuggestions(current => {
          const next = { ...current }

          for (const item of data.results) {
            // One idempotency key per suggestion, so a repeated click returns
            // the recorded result instead of applying twice.
            next[item.id] = { ...item, operationId: newOperationId() }
          }

          return next
        })
        setProgress({ done: Math.min(start + batch.length, ids.length), total: ids.length })
      }
    } catch (error) {
      if (runRef.current === run) {
        setFindError(errorMessage(error, "Unable to find ratings."))
      }
    } finally {
      if (runRef.current === run) {
        setFinding(false)
        setProgress(null)
      }
    }
  }

  function stopFinding() {
    runRef.current += 1
    setFinding(false)
    setProgress(null)
  }

  function updateSuggestion(id: string, patch: Partial<SuggestionState>) {
    setSuggestions(current => (
      current[id] ? { ...current, [id]: { ...current[id], ...patch } } : current
    ))
  }

  async function applySuggestion(suggestion: SuggestionState) {
    if (!suggestion.apply) {
      return
    }

    updateSuggestion(suggestion.id, { applying: true, error: undefined })

    try {
      await applyMetadataMatch(suggestion.kind, suggestion.id, {
        ...suggestion.apply,
        operation_id: suggestion.operationId,
      })

      updateSuggestion(suggestion.id, { applying: false, applied: true })
      void load(true)
    } catch (error) {
      const stale = error instanceof ApiError && error.status === 409

      updateSuggestion(suggestion.id, {
        applying: false,
        error: stale
          ? "This item changed since the suggestion was made. Find its rating again."
          : errorMessage(error, "Unable to apply this rating."),
      })
    }
  }

  function retrySuggestion(id: string) {
    setSuggestions(current => {
      const next = { ...current }
      delete next[id]
      return next
    })
    void findRatings([id])
  }

  const counts = coverage?.summary[kind]
  const kindInfo = coverage?.kinds.find(item => item.kind === kind)
  const editable = kind === "movie" || kind === "series"
  const ratingOptions = kind === "movie"
    ? [...MOVIE_RATINGS, ...TV_RATINGS]
    : [...TV_RATINGS, ...MOVIE_RATINGS]
  const allSelected = rows.length > 0 && rows.every(row => selected.has(row.id))

  function toggleRow(id: string) {
    setConfirmingManual(false)
    setSelected(current => {
      const next = new Set(current)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  function toggleAll() {
    setConfirmingManual(false)
    setSelected(allSelected ? new Set() : new Set(rows.map(row => row.id)))
  }

  async function saveManualRating() {
    setSavingManual(true)
    setManualMessage(null)
    try {
      const result = await setLibraryRatings(library.id, kind, Array.from(selected), manualRating)
      setManualMessage(
        `${result.rating ? `Set ${result.rating} on` : "Cleared the rating on"} ${result.changed} item${result.changed === 1 ? "" : "s"}`
        + (result.unchanged ? ` (${result.unchanged} already matched).` : "."),
      )
      setSelected(new Set())
      setConfirmingManual(false)
      setSuggestions({})
      void load(true)
    } catch (error) {
      setManualMessage(errorMessage(error, "Unable to set the rating."))
    } finally {
      setSavingManual(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Ratings</CardTitle>
          <CardDescription>
            Content ratings for {library.name}. Media servers such as Jellyfin use these for parental controls.
            Suggested ratings come from your metadata provider and are only saved when you apply them.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {coverage && coverage.kinds.length > 0 && (
            <div className="flex flex-wrap gap-2" role="group" aria-label="Item type">
              {coverage.kinds.map(item => (
                <Button
                  key={item.kind}
                  variant={kind === item.kind ? "default" : "outline"}
                  onClick={() => changeKind(item.kind)}
                >
                  {item.label} ({item.total})
                </Button>
              ))}
            </div>
          )}

          {counts && (
            <div className="grid gap-3 sm:grid-cols-4">
              {(["total", "rated", "missing", "unrecognized"] as const).map(key => (
                <div key={key} className="rounded-md border p-3">
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">
                    {key === "total" ? "Total" : key === "missing" ? "No rating" : STATUS_LABELS[key]}
                  </div>
                  <div className="text-2xl font-semibold">{counts[key]}</div>
                </div>
              ))}
            </div>
          )}

          {coverage && (
            <p className="text-xs text-muted-foreground">
              Recognized ratings: {coverage.recognized_ratings.movie.join(", ")} for movies and{" "}
              {coverage.recognized_ratings.tv.join(", ")} for TV. Anything else (for example a UK
              &quot;15&quot; or &quot;NR&quot;) is listed as unrecognized because a media server may not filter on it.
            </p>
          )}
        </CardContent>
      </Card>

      {kindInfo?.nfo && (
        <>
          <NfoRatingImportCard
            libraryId={library.id}
            kind={kind as MetadataMatchKind}
            onImported={() => {
              setSuggestions({})
              void load(true)
            }}
          />

          <NfoRatingExportCard
            libraryId={library.id}
            kind={kind as MetadataMatchKind}
          />
        </>
      )}

      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="flex flex-wrap gap-2" role="group" aria-label="Rating status">
              {STATUS_FILTERS.map(item => (
                <Button
                  key={item.value}
                  size="sm"
                  variant={status === item.value ? "default" : "outline"}
                  onClick={() => changeStatus(item.value)}
                >
                  {item.label}
                </Button>
              ))}
            </div>

            <form onSubmit={handleSearch} className="flex gap-2">
              <Input
                aria-label="Search titles"
                placeholder="Search titles"
                value={search}
                maxLength={200}
                onChange={event => setSearch(event.target.value)}
              />
              <Button type="submit" variant="outline">Search</Button>
            </form>
          </div>

          {kindInfo && !kindInfo.provider_suggestions && (
            <p className="text-sm text-muted-foreground">
              Metadata providers don&apos;t rate online video, so set these ratings by hand: select channels below and
              choose a rating. In media servers each channel is a TV series, and its videos use the channel&apos;s rating.
            </p>
          )}

          {kindInfo?.provider_suggestions && (
          <div className="flex flex-wrap items-center gap-3">
            {finding ? (
              <>
                <Button disabled>
                  Finding ratings... {progress ? `${progress.done} of ${progress.total}` : ""}
                </Button>
                <Button variant="outline" onClick={stopFinding}>
                  Stop
                </Button>
              </>
            ) : (
              <Button disabled={!pending.length} onClick={() => void findRatings(pending.map(row => row.id))}>
                {pending.length
                  ? `Find ratings for ${pending.length} unrated item${pending.length === 1 ? "" : "s"} on this page`
                  : "No unrated items left on this page"}
              </Button>
            )}
            <span className="text-sm text-muted-foreground">
              Searches your metadata provider in batches of {SUGGESTIONS_PER_REQUEST}. Only confident matches get a
              suggested rating, and nothing is saved until you apply it.
            </span>
          </div>
          )}

          {selected.size > 0 && (
            <div className="space-y-2 rounded-md border p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{selected.size} selected</span>
                <label className="flex items-center gap-2">
                  Rating
                  <select
                    className={SELECT_CLASS}
                    value={manualRating}
                    onChange={event => {
                      setManualRating(event.target.value)
                      setConfirmingManual(false)
                    }}
                  >
                    <option value="">Clear rating</option>
                    {ratingOptions.map(option => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                    <option value="NR">NR (not rated)</option>
                  </select>
                </label>
                {!confirmingManual ? (
                  <Button size="sm" disabled={savingManual} onClick={() => setConfirmingManual(true)}>
                    {manualRating ? `Set ${manualRating}` : "Clear rating"}
                  </Button>
                ) : (
                  <>
                    <Button size="sm" disabled={savingManual} onClick={() => void saveManualRating()}>
                      {savingManual ? "Saving..." : `Confirm for ${selected.size} item${selected.size === 1 ? "" : "s"}`}
                    </Button>
                    <Button size="sm" variant="outline" disabled={savingManual} onClick={() => setConfirmingManual(false)}>
                      Cancel
                    </Button>
                  </>
                )}
                <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
                  Clear selection
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Saved as a manual edit: the rating is locked, so NFO imports and provider suggestions won&apos;t replace it.
              </p>
            </div>
          )}

          {manualMessage && <p className="text-sm" role="status">{manualMessage}</p>}

          {findError && <p className="text-sm text-destructive" role="alert">{findError}</p>}
          {loadError && <p className="text-sm text-destructive" role="alert">{loadError}</p>}
          {loading && !coverage && <p className="text-sm text-muted-foreground">Loading ratings...</p>}

          {coverage && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="w-8 py-2 pr-3">
                      <input
                        type="checkbox"
                        className="size-4"
                        aria-label="Select all on this page"
                        checked={allSelected}
                        onChange={toggleAll}
                      />
                    </th>
                    <th className="py-2 pr-3">Title</th>
                    <th className="py-2 pr-3">Year</th>
                    <th className="py-2 pr-3">Rating</th>
                    <th className="py-2 pr-3">Source</th>
                    <th className="py-2">Suggestion</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(row => (
                    <RatingRow
                      key={row.id}
                      row={row}
                      suggestion={suggestions[row.id]}
                      busy={finding}
                      selected={selected.has(row.id)}
                      onToggle={() => toggleRow(row.id)}
                      onApply={applySuggestion}
                      onRetry={retrySuggestion}
                      onOpen={editable ? () => setEditing({ kind: row.kind as MetadataMatchKind, id: row.id, title: row.title }) : undefined}
                    />
                  ))}
                  {!rows.length && (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-muted-foreground">
                        {status === "missing" ? "Everything here has a rating." : "Nothing matches this filter."}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {coverage && (
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                Items per page
                <select
                  className={SELECT_CLASS}
                  value={pageSize}
                  onChange={event => changePageSize(Number(event.target.value))}
                >
                  {PAGE_SIZES.map(size => (
                    <option key={size} value={size}>{size}</option>
                  ))}
                </select>
              </label>

              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" disabled={coverage.page <= 1} onClick={() => setPage(1)}>
                  First
                </Button>
                <Button variant="outline" size="sm" disabled={coverage.page <= 1} onClick={() => setPage(coverage.page - 1)}>
                  Previous
                </Button>
                <span className="text-sm text-muted-foreground">
                  Page {coverage.page} of {Math.max(1, Math.ceil(coverage.total / coverage.page_size))}
                  {" "}· {coverage.total} item{coverage.total === 1 ? "" : "s"}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!coverage.next_page}
                  onClick={() => setPage(coverage.next_page ?? coverage.page)}
                >
                  Next
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!coverage.next_page}
                  onClick={() => setPage(Math.max(1, Math.ceil(coverage.total / coverage.page_size)))}
                >
                  Last
                </Button>
              </div>
            </div>
          )}

          {attribution && (
            <p className="border-t pt-3 text-xs text-muted-foreground">{attribution}</p>
          )}
        </CardContent>
      </Card>

      <CatalogItemEditorDialog
        key={editing?.id ?? "closed"}
        kind={editing?.kind ?? null}
        id={editing?.id ?? null}
        onClose={() => setEditing(null)}
        onChanged={() => load(true)}
        initialTab="match"
        matchOptions={{
          autoSearch: true,
          quickRating: true,
          onRatingSaved: rating => {
            // Saved: go straight back to the Ratings list.
            const saved = editing
            setEditing(null)
            if (saved) {
              setSuggestions(current => {
                const next = { ...current }
                delete next[saved.id]
                return next
              })
              setManualMessage(`Saved ${rating} for ${saved.title}.`)
            }
            void load(true)
          },
        }}
      />
    </div>
  )
}


function RatingRow({
  row,
  suggestion,
  busy,
  selected,
  onToggle,
  onApply,
  onRetry,
  onOpen,
}: {
  row: RatingCoverageRow
  suggestion?: SuggestionState
  busy: boolean
  selected: boolean
  onToggle: () => void
  onApply: (suggestion: SuggestionState) => void
  onRetry: (id: string) => void
  onOpen?: () => void
}) {
  return (
    <tr className="border-t align-top">
      <td className="py-2 pr-3">
        <input
          type="checkbox"
          className="mt-1 size-4"
          aria-label={`Select ${row.title}`}
          checked={selected}
          onChange={onToggle}
        />
      </td>
      <td className="py-2 pr-3">
        {onOpen ? (
          <button
            type="button"
            className="text-left font-medium underline-offset-4 hover:underline"
            onClick={onOpen}
          >
            {row.title}
          </button>
        ) : (
          <span className="font-medium">{row.title}</span>
        )}
      </td>
      <td className="py-2 pr-3">{row.year ?? "—"}</td>
      <td className="py-2 pr-3">
        <div className="font-medium">{row.content_rating || "—"}</div>
        {row.status !== "rated" && (
          <Badge variant={row.status === "unrecognized" ? "destructive" : "secondary"}>
            {STATUS_LABELS[row.status]}
          </Badge>
        )}
      </td>
      <td className="py-2 pr-3 text-muted-foreground">
        {row.source_label ?? "—"}
        {row.locked ? " · locked" : ""}
      </td>
      <td className="py-2">
        <SuggestionCell suggestion={suggestion} busy={busy} onApply={onApply} onRetry={onRetry} onOpen={onOpen ?? (() => undefined)} />
      </td>
    </tr>
  )
}


function SuggestionCell({
  suggestion,
  busy,
  onApply,
  onRetry,
  onOpen,
}: {
  suggestion?: SuggestionState
  busy: boolean
  onApply: (suggestion: SuggestionState) => void
  onRetry: (id: string) => void
  onOpen: () => void
}) {
  if (!suggestion) {
    return <span className="text-muted-foreground">—</span>
  }

  const candidate = suggestion.candidate

  if (suggestion.applied) {
    return <span className="font-medium text-emerald-600 dark:text-emerald-400">Applied {suggestion.rating}</span>
  }

  return (
    <div className="space-y-1">
      {suggestion.status === "suggested" && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{suggestion.rating}</span>
          <Button size="sm" disabled={suggestion.applying} onClick={() => onApply(suggestion)}>
            {suggestion.applying ? "Applying..." : `Apply ${suggestion.rating}`}
          </Button>
        </div>
      )}

      {candidate && (
        <div className="text-xs text-muted-foreground">
          Match: {candidate.title} ({candidate.year ?? "year unknown"}) · {candidate.match.reasons.map(reason => reason.label).join(", ")}
        </div>
      )}

      {suggestion.message && (
        <div className="text-xs text-muted-foreground">{suggestion.message}</div>
      )}

      {suggestion.error && (
        <div className="space-y-1" role="alert">
          <div className="text-xs text-destructive">{suggestion.error}</div>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => onRetry(suggestion.id)}>
            Find again
          </Button>
        </div>
      )}

      {suggestion.status !== "suggested" && (
        <Button size="sm" variant="outline" onClick={onOpen}>
          Find match
        </Button>
      )}
    </div>
  )
}
