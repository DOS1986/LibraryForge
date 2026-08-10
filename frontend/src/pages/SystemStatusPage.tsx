import {
  useCallback,
  useEffect,
  useState,
} from "react"

import {
  Badge,
} from "@/components/ui/badge"

import {
  Button,
} from "@/components/ui/button"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import {
  getSystemStatus,
} from "@/lib/api"

import type {
  SystemStatus,
} from "@/types"


function StateBadge({
  ok,
  label,
}: {
  ok: boolean
  label: string
}) {
  return (
    <Badge variant={ok ? "secondary" : "destructive"}>
      {label}
    </Badge>
  )
}


export function SystemStatusPage() {
  const [system, setSystem] =
    useState<SystemStatus | null>(null)

  const [loading, setLoading] =
    useState(true)

  const [error, setError] =
    useState<string | null>(null)


  const load = useCallback(
    async () => {
      setLoading(true)
      setError(null)

      try {
        setSystem(
          await getSystemStatus(),
        )
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load system status.",
        )
      } finally {
        setLoading(false)
      }
    },
    [],
  )


  useEffect(
    () => {
      void load()
    },
    [load],
  )


  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle>System Status</CardTitle>
              <CardDescription className="mt-2">
                Runtime, dependency, and restart-supervisor information for this LibraryForge instance.
              </CardDescription>
            </div>

            <Button
              type="button"
              variant="outline"
              onClick={() => void load()}
              disabled={loading}
            >
              Refresh
            </Button>
          </div>
        </CardHeader>
      </Card>

      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {system && (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Database
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <StateBadge
                  ok={system.database.status === "ok"}
                  label={system.database.status === "ok" ? "Connected" : "Error"}
                />
                <div className="text-sm text-muted-foreground">
                  {system.database.detail}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  ffprobe
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <StateBadge
                  ok={system.ffprobe.status === "ok"}
                  label={system.ffprobe.status === "ok" ? "Available" : "Missing"}
                />
                <div className="break-all text-sm text-muted-foreground">
                  {system.ffprobe.resolved_path || system.ffprobe.configured_path}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Restart Supervisor
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <StateBadge
                  ok={system.restart.supported}
                  label={system.restart.supported ? "Available" : "Not configured"}
                />
                {system.restart.last_requested_at && (
                  <div className="text-sm text-muted-foreground">
                    Last requested {new Date(system.restart.last_requested_at).toLocaleString()}
                    {system.restart.last_requested_by
                      ? ` by ${system.restart.last_requested_by}`
                      : ""}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Build Identity</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div>
                <div className="text-xs uppercase tracking-wide text-muted-foreground">
                  Version
                </div>
                <div className="mt-1 font-medium">
                  {system.version.version}
                </div>
              </div>

              <div>
                <div className="text-xs uppercase tracking-wide text-muted-foreground">
                  Environment
                </div>
                <div className="mt-1 font-medium">
                  {system.version.environment}
                </div>
              </div>

              <div>
                <div className="text-xs uppercase tracking-wide text-muted-foreground">
                  Git
                </div>
                <div className="mt-1 font-medium">
                  {system.version.git_short_sha || "unknown"}
                  {system.version.git_dirty ? " · dirty" : ""}
                </div>
              </div>

              <div>
                <div className="text-xs uppercase tracking-wide text-muted-foreground">
                  Runtime started
                </div>
                <div className="mt-1 font-medium">
                  {new Date(system.version.runtime_started_at).toLocaleString()}
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
