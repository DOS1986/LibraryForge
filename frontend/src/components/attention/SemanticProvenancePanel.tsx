import {
  useEffect,
  useState,
} from "react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import { getSemanticMatchProvenance } from "@/lib/semantic-provenance-api"

import type {
  SemanticFieldProvenance,
  SemanticMatchProvenance,
} from "@/types"


function FieldStateRow({
  state,
}: {
  state: SemanticFieldProvenance
}) {
  return (
    <div className="grid gap-2 border-b py-3 last:border-0 md:grid-cols-[180px_160px_minmax(0,1fr)]">
      <div className="font-medium">{state.field_name}</div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{state.source_label || state.source}</Badge>
        {state.locked && <Badge>Locked</Badge>}
      </div>
      <div className="min-w-0">
        <div className="break-words text-sm">
          {typeof state.value_snapshot === "string"
            ? state.value_snapshot || "—"
            : JSON.stringify(state.value_snapshot)}
        </div>
        {state.source_ref && (
          <div className="mt-1 break-all font-mono text-xs text-muted-foreground">
            {state.source_ref}
          </div>
        )}
      </div>
    </div>
  )
}


export function SemanticProvenancePanel({
  matchId,
}: {
  matchId: string
}) {
  const [data, setData] = useState<SemanticMatchProvenance | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    setLoading(true)
    setError(null)

    getSemanticMatchProvenance(matchId)
      .then(result => {
        if (!cancelled) {
          setData(result)
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load provenance.",
          )
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [matchId])

  if (loading) {
    return <div className="text-sm text-muted-foreground">Loading provenance...</div>
  }

  if (error) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
        {error}
      </div>
    )
  }

  if (!data) {
    return null
  }

  const targetGroups = Object.entries(data.field_states)

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Semantic Identity</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">
              {data.match.source_label || data.match.source || "No source"}
            </Badge>
            <Badge variant="secondary">
              {Math.round(data.match.confidence * 100)}% confidence
            </Badge>
            {data.match.locked && <Badge>Locked</Badge>}
          </div>

          {data.current_identity ? (
            <pre className="max-h-56 overflow-auto rounded-md bg-muted p-3 text-xs">
              {JSON.stringify(data.current_identity, null, 2)}
            </pre>
          ) : (
            <div className="text-muted-foreground">No current semantic identity is assigned.</div>
          )}
        </CardContent>
      </Card>

      {targetGroups.map(([target, states]) => (
        <Card key={target}>
          <CardHeader>
            <CardTitle className="text-base">
              {target.replaceAll("_", " ")} field provenance
            </CardTitle>
          </CardHeader>
          <CardContent>
            {states.length === 0 ? (
              <div className="text-sm text-muted-foreground">
                No field-level provenance has been recorded for this target.
              </div>
            ) : (
              states.map(state => (
                <FieldStateRow key={state.id} state={state} />
              ))
            )}
          </CardContent>
        </Card>
      ))}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Indexed Metadata Sources</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {data.metadata_sources.length === 0 ? (
            <div className="text-sm text-muted-foreground">No indexed metadata sources.</div>
          ) : (
            data.metadata_sources.map(source => (
              <div key={source.id} className="rounded-md border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="font-medium">{source.source_type_label}</div>
                  <Badge variant="outline">{source.status_label}</Badge>
                </div>
                <div className="mt-1 break-all text-xs text-muted-foreground">
                  {source.relative_path}
                </div>
                {Object.keys(source.extracted_data).length > 0 && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs font-medium">
                      Extracted values
                    </summary>
                    <pre className="mt-2 max-h-48 overflow-auto rounded-md bg-muted p-3 text-xs">
                      {JSON.stringify(source.extracted_data, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}
