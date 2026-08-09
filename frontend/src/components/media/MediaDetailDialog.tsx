import {
  useEffect,
  useState,
} from "react"

import {
  Badge,
} from "@/components/ui/badge"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import {
  Dialog,
  DialogTitle,
} from "@/components/ui/dialog"

import {
  ScrollableDialogBody,
  ScrollableDialogContent,
  ScrollableDialogHeader,
} from "@/components/dialogs/ScrollableDialog"

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
  getMediaItem,
} from "@/lib/api"

import {
  formatBytes,
  formatDateTime,
  formatDuration,
} from "@/lib/format"

import type {
  MediaItemDetail,
} from "@/types"


interface MediaDetailDialogProps {
  mediaItemId:
    | string
    | null

  onClose:
    () => void
}


export function MediaDetailDialog({
  mediaItemId,
  onClose,
}: MediaDetailDialogProps) {
  const [
    item,
    setItem,
  ] = useState<
    MediaItemDetail
    | null
  >(null)

  const [
    loading,
    setLoading,
  ] = useState(false)


  useEffect(
    () => {
      if (!mediaItemId) {
        setItem(null)
        return
      }

      let cancelled = false

      setLoading(true)

      getMediaItem(
        mediaItemId
      )
        .then(
          (
            result
          ) => {
            if (!cancelled) {
              setItem(
                result
              )
            }
          }
        )
        .finally(
          () => {
            if (!cancelled) {
              setLoading(
                false
              )
            }
          }
        )

      return () => {
        cancelled = true
      }
    },
    [
      mediaItemId,
    ],
  )


  return (
    <Dialog
      open={
        mediaItemId
        !== null
      }
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
      <ScrollableDialogContent>
        {loading && (
          <ScrollableDialogBody
            className="
              flex
              items-center
              justify-center
              text-muted-foreground
            "
          >
            Loading media details...
          </ScrollableDialogBody>
        )}

        {
          !loading
          && item
          && (
            <>
              <ScrollableDialogHeader>
                <DialogTitle>
                  {item.title}
                </DialogTitle>
              </ScrollableDialogHeader>

              <ScrollableDialogBody>
                <Tabs
                  defaultValue="overview"
                  className="
                    min-w-0
                  "
                >
                <TabsList
                  className="
                    sticky
                    top-0
                    z-10
                    grid
                    w-full
                    grid-cols-5
                    bg-background
                  "
                >
                  <TabsTrigger
                    value="overview"
                  >
                    Overview
                  </TabsTrigger>

                  <TabsTrigger
                    value="technical"
                  >
                    Technical
                  </TabsTrigger>

                  <TabsTrigger
                    value="metadata"
                  >
                    Metadata
                  </TabsTrigger>

                  <TabsTrigger
                    value="files"
                  >
                    Files
                  </TabsTrigger>

                  <TabsTrigger
                    value="history"
                  >
                    History
                  </TabsTrigger>
                </TabsList>

                <TabsContent
                  value="overview"
                  className="
                    space-y-5
                    pt-4
                  "
                >
                  <div
                    className="
                      grid
                      gap-4
                      md:grid-cols-2
                    "
                  >
                    <div>
                      <div
                        className="
                          text-sm
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
                        {item.title}
                      </div>
                    </div>

                    <div>
                      <div
                        className="
                          text-sm
                          text-muted-foreground
                        "
                      >
                        Media Type
                      </div>

                      <div
                        className="
                          font-medium
                        "
                      >
                        {
                          item
                            .media_type_label
                        }
                      </div>
                    </div>

                    <div>
                      <div
                        className="
                          text-sm
                          text-muted-foreground
                        "
                      >
                        Release Date
                      </div>

                      <div
                        className="
                          font-medium
                        "
                      >
                        {
                          item.release_date
                          ?? "—"
                        }
                      </div>
                    </div>
                  </div>

                  <Separator />

                  <div>
                    <div
                      className="
                        text-sm
                        text-muted-foreground
                      "
                    >
                      Description
                    </div>

                    <div
                      className="
                        mt-1
                        whitespace-pre-wrap
                      "
                    >
                      {
                        item.description
                        || "—"
                      }
                    </div>
                  </div>
                </TabsContent>

                <TabsContent
                  value="technical"
                  className="
                    space-y-3
                    pt-4
                  "
                >
                  {
                    item.files.map(
                      (
                        file
                      ) => (
                        <Card
                          key={
                            file.id
                          }
                        >
                          <CardHeader>
                            <CardTitle
                              className="
                                text-base
                              "
                            >
                              {
                                file.file_name
                              }
                            </CardTitle>

                            <CardDescription>
                              {
                                file.relative_path
                              }
                            </CardDescription>
                          </CardHeader>

                          <CardContent
                            className="
                              grid
                              gap-4
                              md:grid-cols-3
                            "
                          >
                            <div>
                              Video:
                              {" "}
                              <strong>
                                {
                                  file.video_codec
                                  || "—"
                                }
                              </strong>
                            </div>

                            <div>
                              Resolution:
                              {" "}
                              <strong>
                                {
                                  file.width
                                  && file.height
                                    ? `${file.width}×${file.height}`
                                    : "—"
                                }
                              </strong>
                            </div>

                            <div>
                              Audio:
                              {" "}
                              <strong>
                                {
                                  file.audio_codec
                                  || "—"
                                }
                              </strong>
                            </div>

                            <div>
                              Duration:
                              {" "}
                              <strong>
                                {
                                  formatDuration(
                                    file.duration_seconds
                                  )
                                }
                              </strong>
                            </div>

                            <div>
                              Size:
                              {" "}
                              <strong>
                                {
                                  formatBytes(
                                    file.size_bytes
                                  )
                                }
                              </strong>
                            </div>

                            <div>
                              Container:
                              {" "}
                              <strong>
                                {
                                  file.container_format
                                  || "—"
                                }
                              </strong>
                            </div>
                          </CardContent>
                        </Card>
                      )
                    )
                  }
                </TabsContent>

                <TabsContent
                  value="metadata"
                  className="
                    space-y-5
                    pt-4
                  "
                >
                  <section>
                    <h3
                      className="
                        text-lg
                        font-semibold
                      "
                    >
                      Canonical Metadata
                    </h3>

                    <div
                      className="
                        mt-3
                        grid
                        gap-3
                        md:grid-cols-2
                      "
                    >
                      <div>
                        Title:
                        {" "}
                        <strong>
                          {item.title}
                        </strong>
                      </div>

                      <div>
                        Type:
                        {" "}
                        <strong>
                          {
                            item
                              .media_type_label
                          }
                        </strong>
                      </div>

                      <div>
                        Release:
                        {" "}
                        <strong>
                          {
                            item.release_date
                            ?? "—"
                          }
                        </strong>
                      </div>

                      <div>
                        Tags:
                        {" "}
                        <strong>
                          {
                            item.tags.length
                              ? item.tags.join(
                                ", "
                              )
                              : "—"
                          }
                        </strong>
                      </div>
                    </div>
                  </section>

                  <Separator />

                  <section>
                    <h3
                      className="
                        text-lg
                        font-semibold
                      "
                    >
                      Metadata Sources
                    </h3>

                    <div
                      className="
                        mt-3
                        space-y-3
                      "
                    >
                      {
                        item
                          .metadata_sources
                          .map(
                            (
                              source
                            ) => (
                              <div
                                key={
                                  source.id
                                }
                                className="
                                  rounded-md
                                  border
                                  p-3
                                "
                              >
                                <div
                                  className="
                                    flex
                                    items-center
                                    justify-between
                                    gap-4
                                  "
                                >
                                  <strong>
                                    {
                                      source
                                        .source_type_label
                                    }
                                  </strong>

                                  <Badge
                                    variant={
                                      source.status
                                      === "detected"
                                        ? "secondary"
                                        : source.status
                                          === "error"
                                          ? "destructive"
                                          : "outline"
                                    }
                                  >
                                    {
                                      source.status
                                      === "detected"
                                        ? "✓ Detected"
                                        : source
                                            .status_label
                                    }
                                  </Badge>
                                </div>

                                {
                                  Object.keys(
                                    source
                                      .extracted_data
                                  ).length
                                  > 0
                                  && (
                                    <pre
                                      className="
                                        mt-3
                                        max-h-60
                                        max-w-full
                                        overflow-auto
                                        rounded
                                        bg-muted
                                        p-3
                                        text-xs
                                      "
                                    >
                                      {
                                        JSON.stringify(
                                          source
                                            .extracted_data,
                                          null,
                                          2,
                                        )
                                      }
                                    </pre>
                                  )
                                }
                              </div>
                            )
                          )
                      }
                    </div>
                  </section>
                </TabsContent>

                <TabsContent
                  value="files"
                  className="
                    space-y-3
                    pt-4
                  "
                >
                  {
                    item.files.map(
                      (
                        file
                      ) => (
                        <div
                          key={
                            file.id
                          }
                          className="
                            rounded-md
                            border
                            p-3
                          "
                        >
                          <div
                            className="
                              font-medium
                            "
                          >
                            {
                              file.file_name
                            }
                          </div>

                          <div
                            className="
                              break-all
                              text-sm
                              text-muted-foreground
                            "
                          >
                            {
                              file.relative_path
                            }
                          </div>
                        </div>
                      )
                    )
                  }
                </TabsContent>

                <TabsContent
                  value="history"
                  className="
                    space-y-3
                    pt-4
                  "
                >
                  <div>
                    Created:
                    {" "}
                    {
                      formatDateTime(
                        item.created_at
                      )
                    }
                  </div>

                  {
                    item
                      .metadata_sources
                      .map(
                        (
                          source
                        ) => (
                          <div
                            key={
                              source.id
                            }
                            className="
                              border-l-2
                              pl-3
                            "
                          >
                            {
                              source
                                .source_type_label
                            }
                            {" checked — "}
                            {
                              formatDateTime(
                                source
                                  .last_checked_at
                              )
                            }
                          </div>
                        )
                      )
                  }
                </TabsContent>
                </Tabs>
              </ScrollableDialogBody>
            </>
          )
        }
      </ScrollableDialogContent>
    </Dialog>
  )
}
