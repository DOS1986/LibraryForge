import {
  useMemo,
  useState,
} from "react"

import {
  AlertTriangle,
  CheckCircle2,
  LockKeyhole,
} from "lucide-react"

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

import {
  Dialog,
  DialogTitle,
} from "@/components/ui/dialog"

import {
  Separator,
} from "@/components/ui/separator"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"

import {
  ScrollableDialogBody,
  ScrollableDialogContent,
  ScrollableDialogHeader,
} from "@/components/dialogs/ScrollableDialog"

import {
  ManualMatchForm,
} from "@/components/attention/ManualMatchForm"

import {
  SemanticCandidateCard,
} from "@/components/attention/SemanticCandidateCard"

import {
  resetSemanticMatch,
  resolveSemanticMatch,
  setSemanticMatchLock,
} from "@/lib/api"

import {
  formatBytes,
  formatDuration,
} from "@/lib/format"

import {
  getConflictCandidate,
  getSuggestedCandidate,
  readSemanticCandidate,
} from "@/lib/semantic"

import type {
  Library,
  SemanticMatch,
  SemanticResolveInput,
} from "@/types"


interface SemanticMatchDialogProps {
  library: Library

  match:
    | SemanticMatch
    | null

  onClose:
    () => void

  onChanged:
    () => Promise<void>
}


function assignmentLabel(
  match: SemanticMatch,
) {
  const assignment =
    match.current_assignment

  if (!assignment) {
    return "No semantic assignment"
  }

  if (
    assignment.kind
    === "movie"
  ) {
    return (
      assignment.year
        ? (
          `${assignment.title} `
          + `(${assignment.year})`
        )
        : assignment.title
    )
  }

  return (
    `${assignment.series_title || "Unknown Series"} `
    + `S${String(
      assignment.season_number
      ?? 0
    ).padStart(
      2,
      "0",
    )}`
    + `E${String(
      assignment.episode_number
      ?? 0
    ).padStart(
      2,
      "0",
    )}`
    + (
      assignment.title
        ? ` — ${assignment.title}`
        : ""
    )
  )
}


export function SemanticMatchDialog({
  library,
  match,
  onClose,
  onChanged,
}: SemanticMatchDialogProps) {
  const [
    busy,
    setBusy,
  ] = useState(false)

  const [
    error,
    setError,
  ] = useState<
    string | null
  >(null)


  const nfoCandidate =
    useMemo(
      () =>
        match
          ? getConflictCandidate(
            match,
            "nfo",
          )
          : null,
      [
        match,
      ],
    )


  const filenameCandidate =
    useMemo(
      () =>
        match
          ? getConflictCandidate(
            match,
            "filename",
          )
          : null,
      [
        match,
      ],
    )


  const suggestedCandidate =
    useMemo(
      () =>
        match
          ? getSuggestedCandidate(
            match
          )
          : null,
      [
        match,
      ],
    )


  const selectedCandidate =
    useMemo(
      () => {
        if (!match) {
          return null
        }

        return (
          readSemanticCandidate(
            match.candidate_data[
              "selected"
            ]
          )
          || suggestedCandidate
          || nfoCandidate
          || filenameCandidate
        )
      },
      [
        match,
        suggestedCandidate,
        nfoCandidate,
        filenameCandidate,
      ],
    )


  if (!match) {
    return null
  }

  const matchId =
  match.id

  async function run(
    operation:
      () => Promise<unknown>,
  ) {
    setBusy(true)
    setError(null)

    try {
      await operation()

      await onChanged()

      onClose()

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to update semantic match."
      )

    } finally {
      setBusy(false)
    }
  }


  function useCandidate(
    source:
      | "nfo"
      | "filename"
      | "suggested",
  ) {
    return run(
      () =>
        resolveSemanticMatch(
            matchId,
          {
            candidate_source:
              source,

            lock:
              true,

            notes:
              (
                "Confirmed from "
                + source
                + " candidate."
              ),
          },
        )
    )
  }


  async function manualResolve(
    input: SemanticResolveInput,
  ) {
    await run(
      () =>
        resolveSemanticMatch(
          matchId,
          input,
        )
    )
  }


  return (
    <Dialog
      open
      onOpenChange={
        (
          open
        ) => {
          if (!open) {
            onClose()
          }
        }
      }
    >
      <ScrollableDialogContent
        className="
          !max-w-[1500px]
          sm:!max-w-[1500px]
        "
      >
        <ScrollableDialogHeader>
          <div
            className="
              flex
              flex-wrap
              items-start
              justify-between
              gap-3
              pr-4
            "
          >
            <div
              className="
                min-w-0
              "
            >
              <DialogTitle>
                {
                  match.file_name
                }
              </DialogTitle>

              <div
                className="
                  mt-1
                  max-w-[1000px]
                  break-all
                  text-xs
                  text-muted-foreground
                "
              >
                {
                  match.relative_path
                }
              </div>
            </div>

            <div
              className="
                flex
                flex-wrap
                gap-2
              "
            >
              <Badge
                variant={
                  match.status
                  === "conflict"
                    ? "destructive"
                    : match.status
                      === "unresolved"
                      ? "outline"
                      : "secondary"
                }
              >
                {
                  match.status_label
                }
              </Badge>

              {
                match.locked
                && (
                  <Badge>
                    <LockKeyhole
                      className="
                        mr-1
                        h-3.5
                        w-3.5
                      "
                    />
                    Locked
                  </Badge>
                )
              }
            </div>
          </div>
        </ScrollableDialogHeader>

        <ScrollableDialogBody>
          <div
            className="
              grid
              min-w-0
              gap-6
              xl:grid-cols-[340px_minmax(0,1fr)]
            "
          >
            <div
              className="
                min-w-0
                space-y-4
              "
            >
              <Card>
                <CardHeader>
                  <CardTitle
                    className="
                      text-base
                    "
                  >
                    Physical File
                  </CardTitle>
                </CardHeader>

                <CardContent
                  className="
                    space-y-3
                    text-sm
                  "
                >
                  <div>
                    <div
                      className="
                        text-muted-foreground
                      "
                    >
                      Size
                    </div>

                    <div>
                      {
                        formatBytes(
                          match.size_bytes
                        )
                      }
                    </div>
                  </div>

                  <div>
                    <div
                      className="
                        text-muted-foreground
                      "
                    >
                      Duration
                    </div>

                    <div>
                      {
                        formatDuration(
                          match.duration_seconds
                        )
                      }
                    </div>
                  </div>

                  <div>
                    <div
                      className="
                        text-muted-foreground
                      "
                    >
                      Video
                    </div>

                    <div>
                      {
                        match.video_codec
                        || "—"
                      }

                      {
                        match.width
                        && match.height
                          ? (
                            ` · ${match.width}`
                            + `×${match.height}`
                          )
                          : ""
                      }
                    </div>
                  </div>

                  <Separator />

                  <div>
                    <div
                      className="
                        text-muted-foreground
                      "
                    >
                      Current Assignment
                    </div>

                    <div
                      className="
                        mt-1
                        font-medium
                      "
                    >
                      {
                        assignmentLabel(
                          match
                        )
                      }
                    </div>
                  </div>

                  <div>
                    <div
                      className="
                        text-muted-foreground
                      "
                    >
                      Match Source
                    </div>

                    <div>
                      {
                        match.source_label
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
                      Confidence
                    </div>

                    <div>
                      {
                        `${Math.round(
                          match.confidence
                          * 100
                        )}%`
                      }
                    </div>
                  </div>

                  {
                    match.notes
                    && (
                      <div>
                        <div
                          className="
                            text-muted-foreground
                          "
                        >
                          Notes
                        </div>

                        <div
                          className="
                            whitespace-pre-wrap
                          "
                        >
                          {
                            match.notes
                          }
                        </div>
                      </div>
                    )
                  }
                </CardContent>
              </Card>

              {
                match.status
                === "conflict"
                && (
                  <div
                    className="
                      rounded-md
                      border
                      border-destructive/40
                      bg-destructive/5
                      p-4
                      text-sm
                    "
                  >
                    <div
                      className="
                        flex
                        gap-2
                      "
                    >
                      <AlertTriangle
                        className="
                          mt-0.5
                          h-4
                          w-4
                          shrink-0
                          text-destructive
                        "
                      />

                      <div>
                        <div
                          className="
                            font-medium
                          "
                        >
                          Metadata conflict
                        </div>

                        <div
                          className="
                            mt-1
                            text-muted-foreground
                          "
                        >
                          NFO and filename/folder
                          metadata identify this file
                          differently. LibraryForge
                          intentionally stopped here
                          instead of guessing.
                        </div>
                      </div>
                    </div>
                  </div>
                )
              }

              {
                match.status
                === "unresolved"
                && (
                  <div
                    className="
                      rounded-md
                      border
                      p-4
                      text-sm
                    "
                  >
                    <div
                      className="
                        font-medium
                      "
                    >
                      Identification incomplete
                    </div>

                    <div
                      className="
                        mt-1
                        text-muted-foreground
                      "
                    >
                      The automatic resolver did not
                      have enough confidence to add
                      this file to the semantic
                      catalog.
                    </div>
                  </div>
                )
              }

              {
                match.locked
                && (
                  <div
                    className="
                      rounded-md
                      border
                      bg-muted/30
                      p-4
                      text-sm
                    "
                  >
                    <div
                      className="
                        flex
                        gap-2
                      "
                    >
                      <CheckCircle2
                        className="
                          mt-0.5
                          h-4
                          w-4
                          shrink-0
                        "
                      />

                      <div>
                        Future scans will preserve
                        this file's confirmed
                        semantic assignment.
                      </div>
                    </div>
                  </div>
                )
              }
            </div>

            <div
              className="
                min-w-0
              "
            >
              {
                match.locked
                  ? (
                    <div
                      className="
                        space-y-5
                      "
                    >
                      <h3
                        className="
                          text-lg
                          font-semibold
                        "
                      >
                        Confirmed Match
                      </h3>

                      {
                        selectedCandidate
                        && (
                          <SemanticCandidateCard
                            label="Confirmed Identity"
                            candidate={
                              selectedCandidate
                            }
                          />
                        )
                      }

                      <div
                        className="
                          flex
                          flex-wrap
                          gap-2
                        "
                      >
                        <Button
                          type="button"
                          variant="outline"
                          disabled={
                            busy
                          }
                          onClick={
                            () =>
                              void run(
                                () =>
                                  setSemanticMatchLock(
                                    match.id,
                                    false,
                                  )
                              )
                          }
                        >
                          Unlock Only
                        </Button>

                        <Button
                          type="button"
                          variant="destructive"
                          disabled={
                            busy
                          }
                          onClick={
                            () =>
                              void run(
                                () =>
                                  resetSemanticMatch(
                                    match.id
                                  )
                              )
                          }
                        >
                          Reset to Automatic
                        </Button>
                      </div>

                      <p
                        className="
                          text-sm
                          text-muted-foreground
                        "
                      >
                        Unlock Only keeps the current
                        assignment but allows a future
                        scan to reconsider it. Reset
                        to Automatic immediately
                        detaches the confirmed
                        assignment and reruns the
                        normal resolver now.
                      </p>
                    </div>
                  )
                  : (
                    <Tabs
                      defaultValue={
                        match.status
                        === "conflict"
                          ? "candidates"
                          : "manual"
                      }
                    >
                      <TabsList>
                        <TabsTrigger
                          value="candidates"
                        >
                          Candidates
                        </TabsTrigger>

                        <TabsTrigger
                          value="manual"
                        >
                          Manual Match
                        </TabsTrigger>

                        <TabsTrigger
                          value="raw"
                        >
                          Raw
                        </TabsTrigger>
                      </TabsList>

                      <TabsContent
                        value="candidates"
                        className="
                          mt-5
                        "
                      >
                        {
                          match.status
                          === "conflict"
                            ? (
                              <div
                                className="
                                  grid
                                  gap-4
                                  lg:grid-cols-2
                                "
                              >
                                <SemanticCandidateCard
                                  label="NFO"
                                  candidate={
                                    nfoCandidate
                                  }
                                  actionLabel="Use NFO & Lock"
                                  disabled={
                                    busy
                                  }
                                  onUse={
                                    () =>
                                      void useCandidate(
                                        "nfo"
                                      )
                                  }
                                />

                                <SemanticCandidateCard
                                  label="Filename / Folder"
                                  candidate={
                                    filenameCandidate
                                  }
                                  actionLabel="Use Filename & Lock"
                                  disabled={
                                    busy
                                  }
                                  onUse={
                                    () =>
                                      void useCandidate(
                                        "filename"
                                      )
                                  }
                                />
                              </div>
                            )
                            : (
                              <SemanticCandidateCard
                                label="Automatic Suggestion"
                                candidate={
                                  suggestedCandidate
                                }
                                actionLabel="Use Suggestion & Lock"
                                disabled={
                                  busy
                                  || !suggestedCandidate
                                  || suggestedCandidate
                                      .kind
                                      === "unknown"
                                }
                                onUse={
                                  () =>
                                    void useCandidate(
                                      "suggested"
                                    )
                                }
                              />
                            )
                        }
                      </TabsContent>

                      <TabsContent
                        value="manual"
                        className="
                          mt-5
                        "
                      >
                        <Card>
                          <CardHeader>
                            <CardTitle
                              className="
                                text-base
                              "
                            >
                              Manual Semantic Match
                            </CardTitle>
                          </CardHeader>

                          <CardContent>
                            <ManualMatchForm
                              library={
                                library
                              }
                              seed={
                                selectedCandidate
                              }
                              busy={
                                busy
                              }
                              onSubmit={
                                manualResolve
                              }
                            />
                          </CardContent>
                        </Card>
                      </TabsContent>

                      <TabsContent
                        value="raw"
                        className="
                          mt-5
                        "
                      >
                        <pre
                          className="
                            max-h-[55vh]
                            max-w-full
                            overflow-auto
                            rounded-md
                            bg-muted
                            p-4
                            text-xs
                          "
                        >
                          {
                            JSON.stringify(
                              match.candidate_data,
                              null,
                              2,
                            )
                          }
                        </pre>
                      </TabsContent>
                    </Tabs>
                  )
              }

              {
                error
                && (
                  <div
                    className="
                      mt-4
                      rounded-md
                      border
                      border-destructive/50
                      bg-destructive/5
                      p-3
                      text-sm
                      text-destructive
                    "
                  >
                    {error}
                  </div>
                )
              }
            </div>
          </div>
        </ScrollableDialogBody>
      </ScrollableDialogContent>
    </Dialog>
  )
}
