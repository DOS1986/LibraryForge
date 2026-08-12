export type IntegrationCapability =
  | "metadata"
  | "artwork"
  | "catalog"
  | "output"

export type IntegrationCredentialMode =
  | "none"
  | "user"
  | "application"
  | "hybrid"

export interface IntegrationFieldDefinition {
  name: string
  label: string
  secret: boolean
  required: boolean
  placeholder: string
  help_text: string
}

export interface IntegrationProviderDefinition {
  key: string
  label: string
  description: string
  capabilities: IntegrationCapability[]
  online_video: boolean
  storage_policy: "none" | "transient"
  credential_mode: IntegrationCredentialMode
  credential_summary: string
  fields: IntegrationFieldDefinition[]
}

export interface IntegrationConnection {
  id: string
  name: string
  provider: string
  provider_label: string
  enabled: boolean
  configuration: Record<string, string>
  configured_secret_fields: string[]
  capabilities: IntegrationCapability[]
  credential_mode: IntegrationCredentialMode
  credential_summary: string
  status: "unknown" | "connected" | "error"
  last_tested_at: string | null
  last_error: string
  created_at: string
  updated_at: string
}

export interface LibraryIntegration {
  id: string
  library: string
  connection: string
  connection_name: string
  provider: string
  provider_label: string
  enabled: boolean
  priority: number
  capabilities: IntegrationCapability[]
  credential_mode: IntegrationCredentialMode
  credential_summary: string
  created_at: string
  updated_at: string
}

interface ConnectionInput {
  name: string
  provider: string
  enabled?: boolean
  configuration: Record<string, string>
  secrets?: Record<string, string>
}

function cookie(name: string) {
  for (const value of document.cookie.split(";")) {
    const item = value.trim()
    if (item.startsWith(`${name}=`)) {
      return decodeURIComponent(item.slice(name.length + 1))
    }
  }
  return null
}

async function api<T>(url: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase()
  const headers = new Headers(options.headers)
  if (options.body) headers.set("Content-Type", "application/json")
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = cookie("csrftoken")
    if (csrf) headers.set("X-CSRFToken", csrf)
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  })
  const text = await response.text()
  const contentType = response.headers.get("content-type") ?? ""
  let data: unknown = undefined
  if (text && contentType.includes("application/json")) {
    try { data = JSON.parse(text) } catch { data = undefined }
  }
  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data
      ? String((data as { detail: unknown }).detail)
      : contentType.includes("application/json") && text
        ? text
        : `Request failed with status ${response.status}.`
    throw new Error(detail)
  }
  return data as T
}

export function getIntegrationProviders() {
  return api<IntegrationProviderDefinition[]>("/api/integrations/providers/")
}

export function getIntegrationConnections() {
  return api<IntegrationConnection[]>("/api/integrations/connections/")
}

export function createIntegrationConnection(input: ConnectionInput) {
  return api<IntegrationConnection>("/api/integrations/connections/", {
    method: "POST",
    body: JSON.stringify(input),
  })
}

export function updateIntegrationConnection(id: string, input: Partial<ConnectionInput>) {
  return api<IntegrationConnection>(`/api/integrations/connections/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(input),
  })
}

export function deleteIntegrationConnection(id: string) {
  return api<void>(`/api/integrations/connections/${id}/`, { method: "DELETE" })
}

export function testIntegrationConnection(id: string) {
  return api<{ ok: boolean; message: string; details?: Record<string, unknown> }>(
    `/api/integrations/connections/${id}/test/`,
    { method: "POST" },
  )
}

export function getLibraryIntegrations(libraryId: string) {
  const params = new URLSearchParams({ library: libraryId })
  return api<LibraryIntegration[]>(`/api/integrations/library-links/?${params}`)
}

export function createLibraryIntegration(input: {
  library: string
  connection: string
  capabilities: IntegrationCapability[]
  priority?: number
}) {
  return api<LibraryIntegration>("/api/integrations/library-links/", {
    method: "POST",
    body: JSON.stringify({ enabled: true, priority: 100, ...input }),
  })
}

export function deleteLibraryIntegration(id: string) {
  return api<void>(`/api/integrations/library-links/${id}/`, { method: "DELETE" })
}
