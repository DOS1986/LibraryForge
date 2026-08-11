import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  createIntegrationConnection,
  deleteIntegrationConnection,
  getIntegrationConnections,
  getIntegrationProviders,
  testIntegrationConnection,
  updateIntegrationConnection,
  type IntegrationConnection,
  type IntegrationCredentialMode,
  type IntegrationProviderDefinition,
} from "@/lib/integration-api"

interface FormState {
  id?: string
  name: string
  provider: string
  configuration: Record<string, string>
  secrets: Record<string, string>
}

const emptyForm: FormState = {
  name: "",
  provider: "",
  configuration: {},
  secrets: {},
}

function capabilityLabel(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function credentialModeLabel(value: IntegrationCredentialMode) {
  if (value === "none") return "No credentials"
  if (value === "application") return "Built-in / application credential"
  if (value === "hybrid") return "Application + user credential"
  return "User-provided credential"
}

export function IntegrationsPage() {
  const [providers, setProviders] = useState<IntegrationProviderDefinition[]>([])
  const [connections, setConnections] = useState<IntegrationConnection[]>([])
  const [form, setForm] = useState<FormState>(emptyForm)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const provider = useMemo(
    () => providers.find((item) => item.key === form.provider) ?? null,
    [providers, form.provider],
  )

  async function refresh() {
    setLoading(true)
    setError(null)
    try {
      const [providerRows, connectionRows] = await Promise.all([
        getIntegrationProviders(),
        getIntegrationConnections(),
      ])
      setProviders(providerRows)
      setConnections(connectionRows)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load integrations.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void refresh() }, [])

  function startCreate(providerKey = "") {
    setMessage(null)
    setError(null)
    setForm({ ...emptyForm, provider: providerKey })
  }

  function startEdit(connection: IntegrationConnection) {
    setMessage(null)
    setError(null)
    setForm({
      id: connection.id,
      name: connection.name,
      provider: connection.provider,
      configuration: Object.fromEntries(
        Object.entries(connection.configuration ?? {}).map(([key, value]) => [key, String(value ?? "")]),
      ),
      secrets: {},
    })
  }

  async function save() {
    if (!provider) return
    setSaving(true)
    setMessage(null)
    setError(null)
    const payload = {
      name: form.name.trim(),
      provider: provider.key,
      enabled: true,
      configuration: form.configuration,
      secrets: form.secrets,
    }
    try {
      if (form.id) await updateIntegrationConnection(form.id, payload)
      else await createIntegrationConnection(payload)
      setForm(emptyForm)
      setMessage("Integration saved.")
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save integration.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>Settings</CardTitle>
              <CardDescription>Configure LibraryForge and external read-only/provider connections.</CardDescription>
            </div>
            <div className="flex gap-2">
              <Link to="/settings" className="inline-flex h-9 items-center justify-center whitespace-nowrap rounded-md border border-input bg-background px-4 py-2 text-sm font-medium shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">General</Link>
              <Link to="/settings/integrations" className="inline-flex h-9 items-center justify-center whitespace-nowrap rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring">Integrations</Link>
            </div>
          </div>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Integrations</CardTitle>
          <CardDescription>
            Connections are created once here and then assigned to individual libraries. Integrations may provide metadata, artwork, catalog relationships, or outputs. LibraryForge has no acquisition/download integration capability.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 lg:grid-cols-2">
          {providers.map((item) => (
            <div key={item.key} className="rounded-lg border p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="font-semibold">{item.label}</div>
                  <div className="mt-1 text-sm text-muted-foreground">{item.description}</div>
                </div>
                <Button size="sm" variant="outline" onClick={() => startCreate(item.key)}>Add</Button>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                {item.capabilities.map((capability) => (
                  <span key={capability} className="rounded-full border px-2 py-1">{capabilityLabel(capability)}</span>
                ))}
                {item.storage_policy === "transient" && (
                  <span className="rounded-full border px-2 py-1">Live / transient data</span>
                )}
                <span className="rounded-full border px-2 py-1">{credentialModeLabel(item.credential_mode)}</span>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">{item.credential_summary}</div>
            </div>
          ))}
        </CardContent>
      </Card>

      {(error || message) && (
        <div className={`rounded-md border p-3 text-sm ${error ? "border-destructive/50 text-destructive" : "text-muted-foreground"}`}>
          {error || message}
        </div>
      )}

      {provider && (
        <Card>
          <CardHeader>
            <CardTitle>{form.id ? "Edit" : "Add"} {provider.label}</CardTitle>
            <CardDescription>{provider.credential_summary}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <label className="text-sm font-medium">Connection name</label>
              <Input value={form.name} placeholder={`My ${provider.label}`} onChange={(event) => setForm((value) => ({ ...value, name: event.target.value }))} />
            </div>
            {provider.fields.map((field) => (
              <div key={field.name} className="space-y-2">
                <label className="text-sm font-medium">{field.label}</label>
                <Input
                  type={field.secret ? "password" : "text"}
                  value={field.secret ? (form.secrets[field.name] ?? "") : (form.configuration[field.name] ?? "")}
                  placeholder={field.secret && form.id ? "Leave blank to keep existing value" : field.placeholder}
                  onChange={(event) => {
                    const next = event.target.value
                    setForm((value) => field.secret
                      ? { ...value, secrets: { ...value.secrets, [field.name]: next } }
                      : { ...value, configuration: { ...value.configuration, [field.name]: next } })
                  }}
                />
                {field.help_text && <div className="text-xs text-muted-foreground">{field.help_text}</div>}
              </div>
            ))}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setForm(emptyForm)}>Cancel</Button>
              <Button disabled={saving || !form.name.trim()} onClick={() => void save()}>{saving ? "Saving..." : "Save Integration"}</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Configured Connections</CardTitle>
          <CardDescription>Test connections here, then attach them from a library's Settings → Integrations tab.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {loading ? <div className="text-sm text-muted-foreground">Loading integrations...</div> : null}
          {!loading && connections.length === 0 ? <div className="text-sm text-muted-foreground">No integrations configured yet.</div> : null}
          {connections.map((connection) => (
            <div key={connection.id} className="flex flex-col gap-3 rounded-lg border p-4 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <div className="font-medium">{connection.name}</div>
                <div className="text-sm text-muted-foreground">{connection.provider_label} • {credentialModeLabel(connection.credential_mode)} • {connection.status}</div>
                {connection.last_error && <div className="mt-1 text-xs text-destructive">{connection.last_error}</div>}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={() => startEdit(connection)}>Edit</Button>
                <Button variant="outline" size="sm" onClick={async () => {
                  setError(null); setMessage(null)
                  try { const result = await testIntegrationConnection(connection.id); setMessage(result.message); await refresh() }
                  catch (err) { setError(err instanceof Error ? err.message : "Connection test failed."); await refresh() }
                }}>Test</Button>
                <Button variant="destructive" size="sm" onClick={async () => {
                  if (!window.confirm(`Delete integration "${connection.name}"? Library assignments using it will also be removed.`)) return
                  try { await deleteIntegrationConnection(connection.id); await refresh() }
                  catch (err) { setError(err instanceof Error ? err.message : "Unable to delete integration.") }
                }}>Delete</Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
