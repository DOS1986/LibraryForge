import { useCallback, useEffect, useMemo, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

import { ApiError, getMatchArtwork, saveMatchArtwork } from "@/lib/api"
import { newOperationId } from "@/lib/ids"

import type {
  ArtworkChoice,
  ArtworkChoices,
  ArtworkSource,
  ArtworkTypeKey,
  MetadataMatchKind,
  MetadataMatchPreview,
} from "@/types"


const TYPE_LABELS: Record<ArtworkTypeKey, string> = {
  primary: "Poster",
  backdrop: "Backdrop",
  logo: "Logo",
  banner: "Banner",
  thumb: "Thumb",
}

const TYPE_ORDER: ArtworkTypeKey[] = ["primary", "backdrop", "logo", "banner", "thumb"]

const MAX_SHOWN = 40


function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}


// IDs another artwork source (Fanart.tv) can look this title up by.
function previewIds(preview: MetadataMatchPreview): Record<string, string> {
  const ids: Record<string, string> = {}
  const listed = preview.provider_metadata.external_ids

  if (Array.isArray(listed)) {
    for (const item of listed as { namespace?: unknown; value?: unknown }[]) {
      if (typeof item?.namespace === "string" && typeof item?.value === "string") {
        ids[item.namespace] = item.value
      }
    }
  }

  const own: Record<string, string> = { tmdb: "tmdb", tvdb: "tvdb", omdb: "imdb" }
  const namespace = own[preview.connection.provider]
  if (namespace) {
    ids[namespace] = preview.source_id
  }

  return Object.fromEntries(
    Object.entries(ids).filter(([key]) => key === "tmdb" || key === "imdb" || key === "tvdb"),
  )
}


export function ProviderArtworkPicker({
  kind,
  id,
  preview,
}: {
  kind: MetadataMatchKind
  id: string
  preview: MetadataMatchPreview
}) {
  const ids = useMemo(() => previewIds(preview), [preview])
  const [data, setData] = useState<ArtworkChoices | null>(null)
  const [connection, setConnection] = useState("")
  const [type, setType] = useState<ArtworkTypeKey>("primary")
  const [chosen, setChosen] = useState<ArtworkChoice | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [confirm, setConfirm] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (connectionId: string) => {
    setLoading(true)
    setError(null)

    try {
      const result = await getMatchArtwork(kind, id, {
        connection: connectionId || undefined,
        prefer: connectionId ? undefined : preview.connection.connection_id,
        source_id: preview.source_id,
        ...ids,
      })
      setData(result)
      setConnection(result.connection?.connection_id ?? "")
      setChosen(null)
      setConfirm(null)
      const offered = TYPE_ORDER.filter(key => result.items.some(item => item.artwork_type === key))
      setType(current => (offered.includes(current) ? current : offered[0] ?? "primary"))
    } catch (err) {
      setError(errorMessage(err, "Unable to load artwork."))
    } finally {
      setLoading(false)
    }
  }, [kind, id, preview, ids])

  useEffect(() => {
    void load("")
  }, [load])

  // A details source only knows the title it was matched with.
  const usable = (source: ArtworkSource) => (
    source.mode === "ids"
      ? source.id_namespaces.some(namespace => ids[namespace])
      : source.connection_id === preview.connection.connection_id
  )

  async function save(replace: boolean) {
    if (!chosen || !data?.connection) {
      return
    }

    setSaving(true)
    setError(null)
    setMessage(null)

    try {
      const result = await saveMatchArtwork(kind, id, {
        connection: data.connection.connection_id,
        source_id: data.connection.mode === "details" ? preview.source_id : undefined,
        ids: data.connection.mode === "ids" ? ids : undefined,
        url: chosen.url,
        replace,
        operation_id: newOperationId(),
      })
      setConfirm(null)
      setMessage(
        `Saved ${result.path}.`
        + (result.backups.length
          ? ` Kept ${result.backups.map(item => item.to.split("/").pop()).join(", ")} as a backup.`
          : ""),
      )
      await load(data.connection.connection_id)
    } catch (err) {
      if (err instanceof ApiError && err.code === "existing_artwork") {
        setConfirm(err.message)
      } else {
        setError(errorMessage(err, "Unable to save this artwork."))
      }
    } finally {
      setSaving(false)
    }
  }

  const items = (data?.items ?? []).filter(item => item.artwork_type === type)
  const counts = TYPE_ORDER.map(key => ({
    key,
    count: data?.items.filter(item => item.artwork_type === key).length ?? 0,
  })).filter(item => item.count > 0)
  const current = data?.current[type]
  const blocked = data && (!data.writable || data.root_error || data.folder_error)

  return (
    <section className="space-y-3 rounded-md border p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">Artwork</h3>
        {data && data.sources.length > 0 && (
          <label className="flex items-center gap-2 text-xs">
            Source
            <select
              className="h-8 rounded-md border bg-background px-2 text-sm"
              value={connection}
              disabled={loading || saving}
              onChange={event => void load(event.target.value)}
            >
              {data.sources.filter(usable).map(source => (
                <option key={source.connection_id} value={source.connection_id}>
                  {source.provider_label}
                  {source.connection_name !== source.provider_label ? ` (${source.connection_name})` : ""}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {loading && !data && <p className="text-muted-foreground">Loading artwork...</p>}
      {error && <p className="text-destructive" role="alert">{error}</p>}

      {data && !data.connection && (
        <p className="text-muted-foreground">
          {data.sources.length
            ? `${preview.connection.provider_label} doesn't supply artwork LibraryForge can save. Assign Fanart.tv (or match with TMDB or TheTVDB) to pick artwork.`
            : "No artwork source is assigned to this library. Add TMDB, TheTVDB, or Fanart.tv on the library's Settings tab."}
        </p>
      )}

      {data && !data.writable && (
        <p className="rounded-md border border-amber-500/50 bg-amber-500/10 p-2" role="note">
          This library is Read Only, so artwork can be browsed but not saved. Switch it to Sidecar Only in Settings to save
          artwork beside its files.
        </p>
      )}
      {data?.root_error && <p className="text-destructive" role="alert">{data.root_error}</p>}
      {data?.folder_error && <p className="text-destructive" role="alert">{data.folder_error}</p>}

      {data?.connection && counts.length > 0 && (
        <>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Artwork type">
            {counts.map(item => (
              <Button
                key={item.key}
                size="sm"
                variant={type === item.key ? "default" : "outline"}
                onClick={() => {
                  setType(item.key)
                  setChosen(null)
                  setConfirm(null)
                }}
              >
                {TYPE_LABELS[item.key]} ({item.count})
              </Button>
            ))}
          </div>

          <div className="flex flex-wrap gap-4">
            <div className="space-y-1">
              <div className="text-xs text-muted-foreground">Current</div>
              {current ? (
                <figure className="w-32 space-y-1">
                  <img
                    src={current.content_url}
                    alt={`Current ${TYPE_LABELS[type].toLowerCase()}`}
                    className="max-h-48 w-32 rounded border object-contain"
                    loading="lazy"
                  />
                  <figcaption className="break-all text-xs text-muted-foreground">{current.file_name}</figcaption>
                </figure>
              ) : (
                <div className="flex h-24 w-32 items-center justify-center rounded border text-xs text-muted-foreground">
                  None
                </div>
              )}
            </div>

            <ul className="flex flex-1 flex-wrap gap-2" aria-label={`${TYPE_LABELS[type]} choices`}>
              {items.slice(0, MAX_SHOWN).map(item => {
                const active = chosen?.url === item.url
                return (
                  <li key={item.url}>
                    <button
                      type="button"
                      aria-pressed={active}
                      onClick={() => {
                        setChosen(item)
                        setConfirm(null)
                        setMessage(null)
                      }}
                      className={`w-32 space-y-1 rounded border p-1 text-left focus-visible:outline-2 ${active ? "border-primary ring-2 ring-primary" : ""}`}
                    >
                      <img
                        src={item.thumbnail_url || item.url}
                        alt={`${TYPE_LABELS[type]} option${item.language ? ` (${item.language})` : ""}`}
                        className="max-h-48 w-full rounded object-contain"
                        loading="lazy"
                        referrerPolicy="no-referrer"
                      />
                      <span className="block text-xs text-muted-foreground">
                        {item.width && item.height ? `${item.width}×${item.height}` : "Size unknown"}
                        {item.language ? ` · ${item.language}` : ""}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
          {items.length > MAX_SHOWN && (
            <p className="text-xs text-muted-foreground">Showing {MAX_SHOWN} of {items.length}.</p>
          )}

          {chosen && !blocked && !confirm && (
            <div className="flex flex-wrap items-center gap-2">
              <Button disabled={saving} onClick={() => void save(false)}>
                {saving ? "Saving..." : `Save as ${TYPE_LABELS[type].toLowerCase()}`}
              </Button>
              <span className="text-xs text-muted-foreground">
                Saved as {chosen.file_name} in {data.folder || "the item's folder"}, where Jellyfin reads it.
              </span>
            </div>
          )}

          {confirm && (
            <div className="space-y-2 rounded-md bg-muted/50 p-3" role="alertdialog" aria-label="Replace artwork">
              <p>{confirm}</p>
              <div className="flex gap-2">
                <Button disabled={saving} onClick={() => void save(true)}>
                  {saving ? "Saving..." : "Replace and keep a backup"}
                </Button>
                <Button variant="outline" disabled={saving} onClick={() => setConfirm(null)}>Cancel</Button>
              </div>
            </div>
          )}
        </>
      )}

      {data?.connection && !counts.length && !loading && (
        <p className="text-muted-foreground">{data.connection.provider_label} has no artwork for this title.</p>
      )}

      {message && (
        <p className="text-emerald-700 dark:text-emerald-400" role="status">
          <Badge variant="secondary">Saved</Badge> {message}
        </p>
      )}

      {data?.connection?.attribution && (
        <p className="text-xs text-muted-foreground">{data.connection.attribution}</p>
      )}
    </section>
  )
}
