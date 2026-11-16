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

import {
  getJellyfinLink,
  getJellyfinParentalReport,
  getLibraryIntegrations,
  refreshJellyfinLibrary,
  saveJellyfinLink,
  type JellyfinLink,
  type JellyfinUserReport,
  type LibraryIntegration,
} from "@/lib/integration-api"


function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

const SELECT_CLASS = "h-9 rounded-md border bg-background px-3 text-sm"


/** Library Settings: choose which Jellyfin library a LibraryForge library is. */
export function JellyfinLinkEditor({ linkId }: { linkId: string }) {
  const [data, setData] = useState<JellyfinLink | null>(null)
  const [choice, setChoice] = useState("")
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getJellyfinLink(linkId)
      .then(result => {
        if (cancelled) {
          return
        }
        setData(result)
        setChoice(result.selected_id ?? result.suggested_id ?? "")
      })
      .catch(err => {
        if (!cancelled) {
          setError(errorMessage(err, "Unable to reach Jellyfin."))
        }
      })
    return () => {
      cancelled = true
    }
  }, [linkId])

  async function save() {
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const result = await saveJellyfinLink(linkId, choice)
      setData(result)
      setMessage(choice ? "Saved." : "Link cleared.")
    } catch (err) {
      setError(errorMessage(err, "Unable to save."))
    } finally {
      setSaving(false)
    }
  }

  if (error && !data) {
    return <p className="mt-2 text-sm text-destructive">{error}</p>
  }
  if (!data) {
    return <p className="mt-2 text-sm text-muted-foreground">Loading Jellyfin libraries...</p>
  }

  const changed = choice !== (data.selected_id ?? "")

  return (
    <div className="mt-2 space-y-1 text-sm">
      <label className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground">Jellyfin library</span>
        <select className={SELECT_CLASS} value={choice} onChange={event => setChoice(event.target.value)}>
          <option value="">Not linked</option>
          {data.libraries.map(library => (
            <option key={library.id} value={library.id}>
              {library.name}
              {library.id === data.suggested_id && library.id !== data.selected_id ? " (suggested)" : ""}
            </option>
          ))}
        </select>
        {changed && (
          <Button size="sm" disabled={saving} onClick={() => void save()}>
            {saving ? "Saving..." : "Save"}
          </Button>
        )}
      </label>
      {!data.selected_id && data.suggested_id && (
        <p className="text-xs text-muted-foreground">Suggested by matching folder names. Save to confirm.</p>
      )}
      {message && <p className="text-xs" role="status">{message}</p>}
      {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
    </div>
  )
}


/** Ratings tab: ask Jellyfin to rescan this library after NFO changes. */
export function JellyfinRefreshCard({ libraryId }: { libraryId: string }) {
  const [links, setLinks] = useState<LibraryIntegration[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, { ok: boolean; text: string }>>({})

  useEffect(() => {
    let cancelled = false
    getLibraryIntegrations(libraryId)
      .then(rows => {
        if (!cancelled) {
          setLinks(rows.filter(row => row.provider === "jellyfin"))
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLinks([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [libraryId])

  if (!links.length) {
    return null
  }

  async function refresh(link: LibraryIntegration) {
    setBusy(link.id)
    try {
      const result = await refreshJellyfinLibrary(link.id)
      setResults(current => ({ ...current, [link.id]: { ok: true, text: result.detail } }))
    } catch (err) {
      setResults(current => ({ ...current, [link.id]: { ok: false, text: errorMessage(err, "Refresh failed.") } }))
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Update Jellyfin</CardTitle>
        <CardDescription>
          After writing ratings to NFO files, ask Jellyfin to scan this library so it reads them. This is the same as
          Jellyfin&apos;s &quot;Scan library&quot;: it picks up new and changed files and never replaces existing metadata.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {links.map(link => {
          const linked = Boolean(link.options?.jellyfin_library_id)
          const result = results[link.id]
          return (
            <div key={link.id} className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{link.connection_name}</span>
              {linked ? (
                <Button size="sm" disabled={busy !== null} onClick={() => void refresh(link)}>
                  {busy === link.id ? "Starting..." : "Refresh in Jellyfin"}
                </Button>
              ) : (
                <span className="text-muted-foreground">
                  Choose its Jellyfin library under Library Settings → Integrations first.
                </span>
              )}
              {result && (
                <span className={result.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"} role="status">
                  {result.text}
                </span>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}


function countText(value: number | null) {
  return value === null ? "?" : value.toLocaleString()
}


/** Integrations page: each Jellyfin user's parental controls and what they can see. */
export function JellyfinParentalCheck({ connectionId }: { connectionId: string }) {
  const [users, setUsers] = useState<JellyfinUserReport[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function check() {
    setLoading(true)
    setError(null)
    try {
      setUsers((await getJellyfinParentalReport(connectionId)).users)
    } catch (err) {
      setError(errorMessage(err, "Unable to read Jellyfin users."))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mt-2 space-y-2 text-sm">
      <Button variant="outline" size="sm" disabled={loading} onClick={() => void check()}>
        {loading ? "Checking..." : users ? "Check again" : "Check parental controls"}
      </Button>
      {error && <p className="text-destructive" role="alert">{error}</p>}
      {users && (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="py-1 pr-3">User</th>
                <th className="py-1 pr-3">Maximum rating</th>
                <th className="py-1 pr-3">Blocks unrated</th>
                <th className="py-1 pr-3">Can see</th>
                <th className="py-1">Unrated they can see</th>
              </tr>
            </thead>
            <tbody>
              {users.map(user => (
                <tr key={user.id} className="border-t align-top">
                  <td className="py-1 pr-3">
                    <div className="font-medium">{user.name}</div>
                    <div className="flex gap-1">
                      {user.is_administrator && <Badge variant="secondary">Admin</Badge>}
                      {user.is_disabled && <Badge variant="secondary">Disabled</Badge>}
                    </div>
                  </td>
                  <td className="py-1 pr-3">
                    {user.max_parental_rating === null
                      ? "No limit"
                      : user.max_parental_rating_names.length
                        ? user.max_parental_rating_names.join(" / ")
                        : `Level ${user.max_parental_rating}`}
                  </td>
                  <td className="py-1 pr-3">{user.blocks_unrated.length ? user.blocks_unrated.join(", ") : "Nothing"}</td>
                  <td className="py-1 pr-3">
                    {countText(user.counts.movies.visible)} movies, {countText(user.counts.series.visible)} series
                  </td>
                  <td className="py-1">
                    {countText(user.counts.movies.visible_unrated)} movies, {countText(user.counts.series.visible_unrated)} series
                    {user.warnings.map(warning => (
                      <div key={warning} className="text-xs text-amber-600 dark:text-amber-400">{warning}</div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-muted-foreground">
            Counts come from Jellyfin, applying each user&apos;s own parental controls. &quot;?&quot; means Jellyfin
            didn&apos;t report a count.
          </p>
        </div>
      )}
    </div>
  )
}
