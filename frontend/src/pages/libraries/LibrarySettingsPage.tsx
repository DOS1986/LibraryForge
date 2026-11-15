import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  createLibraryIntegration,
  deleteLibraryIntegration,
  getIntegrationConnections,
  getIntegrationProviders,
  getLibraryIntegrations,
  type IntegrationConnection,
  type IntegrationProviderDefinition,
  type LibraryIntegration,
} from "@/lib/integration-api"
import { updateLibrarySettings } from "@/lib/api"
import { useLibraryOutlet } from "@/lib/route-context"
import { JellyfinLinkEditor } from "@/components/jellyfin/JellyfinPanels"
import type { Library, ManagementMode } from "@/types"


const MODE_OPTIONS: { value: ManagementMode; label: string; description: string }[] = [
  {
    value: "read_only",
    label: "Read Only",
    description: "LibraryForge never changes any file in this library. Use this for archives other apps manage, such as TubeArchivist.",
  },
  {
    value: "sidecar_only",
    label: "Sidecar Only",
    description: "LibraryForge may update sidecar files such as NFOs (for example, writing ratings), but never touches video files.",
  },
  {
    value: "full_control",
    label: "Full Control",
    description: "LibraryForge may also manage the library's media files as file-management features are added. Today it allows the same changes as Sidecar Only.",
  },
]


function ManagementModeEditor({
  library,
  onSaved,
}: {
  library: Library
  onSaved: () => Promise<void>
}) {
  const [mode, setMode] = useState<ManagementMode>(library.management_mode)
  const [confirming, setConfirming] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setMode(library.management_mode)
    setConfirming(false)
    setError(null)
  }, [library.id, library.management_mode])

  const changed = mode !== library.management_mode
  const loosening = library.management_mode === "read_only" && mode !== "read_only"
  const selected = MODE_OPTIONS.find(option => option.value === mode)

  async function save() {
    setSaving(true)
    setError(null)
    try {
      await updateLibrarySettings(library.id, { management_mode: mode })
      await onSaved()
      setConfirming(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to change the management mode.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-2">
      <label htmlFor="management-mode" className="text-sm text-muted-foreground">Management Mode</label>
      <div className="flex flex-wrap items-center gap-2">
        <select
          id="management-mode"
          className="h-9 rounded-md border bg-background px-3 text-sm"
          value={mode}
          disabled={saving}
          onChange={event => {
            setMode(event.target.value as ManagementMode)
            setConfirming(false)
          }}
        >
          {MODE_OPTIONS.map(option => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        {changed && !confirming && (
          <Button
            size="sm"
            disabled={saving}
            onClick={() => (loosening ? setConfirming(true) : void save())}
          >
            Save
          </Button>
        )}
      </div>
      {selected && <p className="text-sm text-muted-foreground">{selected.description}</p>}
      {confirming && (
        <div className="space-y-2 rounded-md bg-muted/50 p-3 text-sm">
          <p>
            Allow LibraryForge to change files under <span className="break-all font-medium">{library.path}</span>?
            Every file change still needs a preview and your confirmation.
          </p>
          <div className="flex gap-2">
            <Button size="sm" disabled={saving} onClick={() => void save()}>
              {saving ? "Saving..." : `Change to ${selected?.label}`}
            </Button>
            <Button size="sm" variant="outline" disabled={saving} onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
    </div>
  )
}


export function LibrarySettingsPage() {
  const { library, refreshLibraries } = useLibraryOutlet()
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = searchParams.get("tab") === "integrations" ? "integrations" : "general"

  const [connections, setConnections] = useState<IntegrationConnection[]>([])
  const [providers, setProviders] = useState<IntegrationProviderDefinition[]>([])
  const [links, setLinks] = useState<LibraryIntegration[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const providerMap = useMemo(
    () => new Map(providers.map((item) => [item.key, item])),
    [providers],
  )

  async function refreshIntegrations() {
    setLoading(true)
    setError(null)
    try {
      const [connectionRows, providerRows, linkRows] = await Promise.all([
        getIntegrationConnections(),
        getIntegrationProviders(),
        getLibraryIntegrations(library.id),
      ])
      setConnections(connectionRows)
      setProviders(providerRows)
      setLinks(linkRows)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load library integrations.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (tab === "integrations") void refreshIntegrations()
  }, [tab, library.id])

  const linkedConnectionIds = new Set(links.map((link) => link.connection))

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>Library Settings</CardTitle>
              <CardDescription>Configuration for {library.name}.</CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                variant={tab === "general" ? "default" : "outline"}
                onClick={() => setSearchParams({})}
              >
                General
              </Button>
              <Button
                variant={tab === "integrations" ? "default" : "outline"}
                onClick={() => setSearchParams({ tab: "integrations" })}
              >
                Integrations
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {tab === "general" ? (
        <Card>
          <CardHeader>
            <CardTitle>General</CardTitle>
            <CardDescription>Current server-visible library configuration.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="text-sm text-muted-foreground">Name</div>
              <div>{library.name}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Path</div>
              <div className="break-all">{library.path}</div>
            </div>
            <ManagementModeEditor library={library} onSaved={refreshLibraries} />
          </CardContent>
        </Card>
      ) : (
        <>
          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Assigned Integrations</CardTitle>
              <CardDescription>
                These connections may enrich metadata/artwork or catalog relationships for this library. They never acquire or download media.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading && links.length === 0 ? <div className="text-sm text-muted-foreground">Loading integrations...</div> : null}
              {!loading && links.length === 0 ? <div className="text-sm text-muted-foreground">No integrations assigned to this library.</div> : null}
              {links.map((link) => (
                <div key={link.id} className="flex flex-col gap-3 rounded-lg border p-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <div className="font-medium">{link.connection_name}</div>
                    <div className="text-sm text-muted-foreground">
                      {link.provider_label} • {link.capabilities.join(", ")}
                    </div>
                    {link.provider === "jellyfin" && <JellyfinLinkEditor linkId={link.id} />}
                  </div>
                  <Button variant="outline" size="sm" onClick={async () => {
                    try {
                      await deleteLibraryIntegration(link.id)
                      await refreshIntegrations()
                    } catch (err) {
                      setError(err instanceof Error ? err.message : "Unable to remove integration.")
                    }
                  }}>
                    Remove
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Available Connections</CardTitle>
              <CardDescription>
                Connections are created once under Settings → Integrations and can then be reused by multiple libraries.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {connections.filter((item) => item.enabled && !linkedConnectionIds.has(item.id)).map((connection) => {
                const definition = providerMap.get(connection.provider)
                if (!definition) return null
                return (
                  <div key={connection.id} className="flex flex-col gap-3 rounded-lg border p-4 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <div className="font-medium">{connection.name}</div>
                      <div className="text-sm text-muted-foreground">
                        {connection.provider_label} • {definition.capabilities.join(", ")}
                      </div>
                    </div>
                    <Button size="sm" onClick={async () => {
                      try {
                        await createLibraryIntegration({
                          library: library.id,
                          connection: connection.id,
                          capabilities: definition.capabilities,
                        })
                        await refreshIntegrations()
                      } catch (err) {
                        setError(err instanceof Error ? err.message : "Unable to assign integration.")
                      }
                    }}>
                      Add to Library
                    </Button>
                  </div>
                )
              })}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
