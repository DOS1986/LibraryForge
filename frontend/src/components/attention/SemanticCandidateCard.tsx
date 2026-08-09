import {
  Badge,
} from "@/components/ui/badge"

import {
  Button,
} from "@/components/ui/button"

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import type {
  SemanticCandidate,
} from "@/types"


interface SemanticCandidateCardProps {
  label: string

  candidate:
    SemanticCandidate
    | null

  actionLabel?: string

  disabled?: boolean

  onUse?:
    () => void
}


function confidenceLabel(
  confidence: number,
) {
  return (
    `${Math.round(
      confidence * 100
    )}%`
  )
}


export function SemanticCandidateCard({
  label,
  candidate,
  actionLabel,
  disabled = false,
  onUse,
}: SemanticCandidateCardProps) {
  return (
    <Card>
      <CardHeader
        className="
          pb-3
        "
      >
        <div
          className="
            flex
            items-start
            justify-between
            gap-3
          "
        >
          <CardTitle
            className="
              text-base
            "
          >
            {label}
          </CardTitle>

          {
            candidate
            && (
              <Badge
                variant="outline"
              >
                {
                  confidenceLabel(
                    candidate
                      .confidence
                  )
                }
              </Badge>
            )
          }
        </div>
      </CardHeader>

      <CardContent
        className="
          space-y-3
          text-sm
        "
      >
        {
          !candidate
          || candidate.kind
          === "unknown"
            ? (
              <div
                className="
                  text-muted-foreground
                "
              >
                No usable semantic candidate.
              </div>
            )
            : candidate.kind
              === "movie"
              ? (
                <>
                  <div>
                    <div
                      className="
                        text-muted-foreground
                      "
                    >
                      Type
                    </div>

                    <div
                      className="
                        font-medium
                      "
                    >
                      Movie
                    </div>
                  </div>

                  <div>
                    <div
                      className="
                        text-muted-foreground
                      "
                    >
                      Title
                    </div>

                    <div
                      className="
                        font-medium
                      "
                    >
                      {
                        candidate.title
                        || "—"
                      }
                    </div>
                  </div>

                  <div>
                    <div
                      className="
                        text-muted-foreground
                      "
                    >
                      Year
                    </div>

                    <div>
                      {
                        candidate.year
                        ?? "—"
                      }
                    </div>
                  </div>

                  {
                    candidate.edition
                    && (
                      <div>
                        <div
                          className="
                            text-muted-foreground
                          "
                        >
                          Edition
                        </div>

                        <div>
                          {
                            candidate.edition
                          }
                        </div>
                      </div>
                    )
                  }
                </>
              )
              : (
                <>
                  <div>
                    <div
                      className="
                        text-muted-foreground
                      "
                    >
                      Type
                    </div>

                    <div
                      className="
                        font-medium
                      "
                    >
                      TV Episode
                    </div>
                  </div>

                  <div>
                    <div
                      className="
                        text-muted-foreground
                      "
                    >
                      Series
                    </div>

                    <div
                      className="
                        font-medium
                      "
                    >
                      {
                        candidate
                          .series_title
                        || "—"
                      }
                    </div>
                  </div>

                  <div
                    className="
                      grid
                      grid-cols-2
                      gap-3
                    "
                  >
                    <div>
                      <div
                        className="
                          text-muted-foreground
                        "
                      >
                        Season
                      </div>

                      <div>
                        {
                          candidate
                            .season_number
                          ?? "—"
                        }
                      </div>
                    </div>

                    <div>
                      <div
                        className="
                          text-muted-foreground
                        "
                      >
                        Episode
                      </div>

                      <div>
                        {
                          candidate
                            .episode_number
                          ?? "—"
                        }

                        {
                          candidate
                            .episode_end_number
                          ? (
                            `–${candidate.episode_end_number}`
                          )
                          : ""
                        }
                      </div>
                    </div>
                  </div>

                  <div>
                    <div
                      className="
                        text-muted-foreground
                      "
                    >
                      Episode Title
                    </div>

                    <div>
                      {
                        candidate
                          .episode_title
                        || candidate.title
                        || "—"
                      }
                    </div>
                  </div>
                </>
              )
        }

        {
          candidate
          && candidate.kind
          !== "unknown"
          && actionLabel
          && onUse
          && (
            <Button
              type="button"
              className="
                w-full
              "
              disabled={
                disabled
              }
              onClick={
                onUse
              }
            >
              {actionLabel}
            </Button>
          )
        }
      </CardContent>
    </Card>
  )
}
