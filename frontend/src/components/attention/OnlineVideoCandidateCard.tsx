import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import type { OnlineVideoSemanticCandidate } from "@/types"


export function OnlineVideoCandidateCard({
  label,
  candidate,
  actionLabel,
  disabled = false,
  onUse,
}: {
  label: string
  candidate: OnlineVideoSemanticCandidate | null
  actionLabel?: string
  disabled?: boolean
  onUse?: () => void
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="text-base">{label}</CardTitle>
          {candidate && (
            <Badge variant="outline">
              {candidate.provider || "unknown"}
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-3 text-sm">
        {!candidate ? (
          <div className="text-muted-foreground">
            No usable Online Video identity from this source.
          </div>
        ) : (
          <>
            <div>
              <div className="text-muted-foreground">Video</div>
              <div className="font-medium">
                {candidate.title || candidate.source_id}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <div className="text-muted-foreground">Provider</div>
                <div>{candidate.provider}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Video ID</div>
                <div className="break-all font-mono text-xs">
                  {candidate.source_id}
                </div>
              </div>
            </div>

            <div>
              <div className="text-muted-foreground">Channel</div>
              <div className="font-medium">
                {candidate.channel_title || "—"}
              </div>
              {candidate.channel_id && (
                <div className="break-all font-mono text-xs text-muted-foreground">
                  {candidate.channel_id}
                </div>
              )}
            </div>

            {candidate.source_url && (
              <div>
                <div className="text-muted-foreground">Source URL</div>
                <div className="break-all text-xs">{candidate.source_url}</div>
              </div>
            )}
          </>
        )}

        {candidate && actionLabel && onUse && (
          <Button
            type="button"
            variant="outline"
            disabled={disabled}
            onClick={onUse}
          >
            {actionLabel}
          </Button>
        )}
      </CardContent>
    </Card>
  )
}
