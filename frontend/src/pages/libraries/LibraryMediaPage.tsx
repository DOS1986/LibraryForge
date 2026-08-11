import {
  useCallback,
  useEffect,
  useState,
} from "react"

import {
  useSearchParams,
} from "react-router-dom"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import {
  Input,
} from "@/components/ui/input"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"

import {
  FolderBrowser,
} from "@/components/library-browser/FolderBrowser"

import {
  SemanticCatalog,
} from "@/components/catalog/SemanticCatalog"

import {
  OnlineVideoCatalog,
} from "@/components/online-video/OnlineVideoCatalog"

import {
  ScanPanel,
} from "@/components/libraries/ScanPanel"

import {
  MediaDetailDialog,
} from "@/components/media/MediaDetailDialog"

import {
  SortHeader,
} from "@/components/media/SortHeader"

import {
  TablePagination,
} from "@/components/tables/TablePagination"

import {
  getMediaFiles,
} from "@/lib/api"

import {
  formatBytes,
  formatDuration,
} from "@/lib/format"

import {
  useLibraryOutlet,
} from "@/lib/route-context"

import type {
  MediaFile,
  MediaSort,
  PageSize,
} from "@/types"


type MediaView =
  | "catalog"
  | "folders"
  | "all"


type MediaFileWithChannel =
  MediaFile & {
    channel_id?: string | null
    channel_title?: string | null
  }


export function LibraryMediaPage() {
  const {
    library,
    refreshLibraries,
  } = useLibraryOutlet()

  const [
    searchParams,
    setSearchParams,
  ] = useSearchParams()

  const requestedView =
    searchParams.get(
      "view"
    )

  const defaultView:
    MediaView = (
      [
        "movies",
        "tv",
        "auto",
        "mixed",
        "online_video",
      ].includes(
        library.content_type
      )
        ? "catalog"
        : "folders"
    )

  const view: MediaView =
    (
      requestedView
      === "catalog"
      || requestedView
      === "folders"
      || requestedView
      === "all"
    )
      ? requestedView
      : defaultView

  const folderPath =
    searchParams.get(
      "folder"
    )
    ?? ""

  const [
    files,
    setFiles,
  ] = useState<
    MediaFileWithChannel[]
  >([])

  const [
    count,
    setCount,
  ] = useState(0)

  const [
    search,
    setSearch,
  ] = useState("")

  const [
    sortField,
    setSortField,
  ] = useState<
    MediaSort
  >(
    "media_item__title"
  )

  const [
    descending,
    setDescending,
  ] = useState(false)

  const [
    page,
    setPage,
  ] = useState(1)

  const [
    pageSize,
    setPageSize,
  ] = useState<
    PageSize
  >(20)

  const [
    totalPages,
    setTotalPages,
  ] = useState(1)

  const [
    selectedMediaItemId,
    setSelectedMediaItemId,
  ] = useState<
    string | null
  >(null)

  const ordering =
    descending
      ? `-${sortField}`
      : sortField


  const loadFlatMedia =
    useCallback(
      async () => {
        const result =
          await getMediaFiles(
            library.id,
            ordering,
            search,
            page,
            pageSize,
          )

        setFiles(
          result.results
        )

        setCount(
          result.count
        )

        setTotalPages(
          result.total_pages
        )
      },
      [
        library.id,
        ordering,
        search,
        page,
        pageSize,
      ],
    )


  useEffect(
    () => {
      if (view === "all") {
        void loadFlatMedia()
      }
    },
    [
      view,
      loadFlatMedia,
    ],
  )


  function setView(
    nextView: MediaView,
  ) {
    const next =
      new URLSearchParams(
        searchParams
      )

    next.set(
      "view",
      nextView
    )

    if (
      nextView
      !== "folders"
    ) {
      next.delete(
        "folder"
      )
    }

    setSearchParams(
      next
    )
  }


  function setFolderPath(
    path: string,
  ) {
    const next =
      new URLSearchParams(
        searchParams
      )

    next.set(
      "view",
      "folders"
    )

    if (path) {
      next.set(
        "folder",
        path,
      )
    } else {
      next.delete(
        "folder"
      )
    }

    setSearchParams(
      next
    )
  }


  function handleSearchChange(
    value: string,
  ) {
    setSearch(value)
    setPage(1)
  }


  function sort(
    field: MediaSort,
  ) {
    setPage(1)

    if (field === sortField) {
      setDescending(
        !descending
      )

      return
    }

    setSortField(field)
    setDescending(false)
  }


  function handlePageSizeChange(
    value: PageSize,
  ) {
    setPageSize(value)
    setPage(1)
  }


  async function handleScanComplete() {
    await Promise.all([
      view === "all"
        ? loadFlatMedia()
        : Promise.resolve(),

      refreshLibraries(),
    ])
  }


  return (
    <>
      <div
        className="
          space-y-6
        "
      >
        <ScanPanel
          library={
            library
          }
          onComplete={
            handleScanComplete
          }
        />

        <Card>
          <CardHeader>
            <CardTitle>
              Media
            </CardTitle>

            <CardDescription>
              Browse the semantic catalog, physical folder hierarchy, or flat sortable media list.
            </CardDescription>
          </CardHeader>

          <CardContent>
            <Tabs
              value={view}
              onValueChange={
                (
                  value
                ) =>
                  setView(
                    (value as MediaView)
                  )
              }
            >
              <TabsList>
                <TabsTrigger
                  value="catalog"
                >
                  Catalog
                </TabsTrigger>

                <TabsTrigger
                  value="folders"
                >
                  Folders
                </TabsTrigger>

                <TabsTrigger
                  value="all"
                >
                  All Media
                </TabsTrigger>
              </TabsList>

              <TabsContent
                value="catalog"
                className="
                  mt-5
                "
              >
                {
                  library.content_type
                  === "online_video"
                    ? (
                      <OnlineVideoCatalog
                        library={library}
                      />
                    )
                    : (
                      <SemanticCatalog
                        library={library}
                      />
                    )
                }
              </TabsContent>

              <TabsContent
                value="folders"
                className="
                  mt-5
                "
              >
                <FolderBrowser
                  libraryId={
                    library.id
                  }
                  path={
                    folderPath
                  }
                  contentMode="media"
                  onPathChange={
                    setFolderPath
                  }
                  onOpenMedia={
                    setSelectedMediaItemId
                  }
                />
              </TabsContent>

              <TabsContent
                value="all"
                className="
                  mt-5
                  space-y-4
                "
              >
                <Input
                  value={search}
                  onChange={
                    (
                      event
                    ) =>
                      handleSearchChange(
                        event
                          .target
                          .value
                      )
                  }
                  placeholder="Search all media..."
                />

                <div
                  className="
                    overflow-x-auto
                  "
                >
                  <table
                    className="
                      w-full
                      min-w-[760px]
                      text-sm
                    "
                  >
                    <thead>
                      <tr
                        className="
                          border-b
                          text-left
                        "
                      >
                        <th
                          className="
                            p-3
                          "
                        >
                          <SortHeader
                            label="Title"
                            field="media_item__title"
                            currentField={
                              sortField
                            }
                            descending={
                              descending
                            }
                            onSort={
                              sort
                            }
                          />
                        </th>

                        {
                          library.content_type
                          === "online_video"
                          && (
                            <th
                              className="
                                p-3
                              "
                            >
                              Channel
                            </th>
                          )
                        }

                        <th
                          className="
                            p-3
                          "
                        >
                          <SortHeader
                            label="Video"
                            field="video_codec"
                            currentField={
                              sortField
                            }
                            descending={
                              descending
                            }
                            onSort={
                              sort
                            }
                          />
                        </th>

                        <th
                          className="
                            p-3
                          "
                        >
                          Resolution
                        </th>

                        <th
                          className="
                            p-3
                          "
                        >
                          <SortHeader
                            label="Duration"
                            field="duration_seconds"
                            currentField={
                              sortField
                            }
                            descending={
                              descending
                            }
                            onSort={
                              sort
                            }
                          />
                        </th>

                        <th
                          className="
                            p-3
                          "
                        >
                          <SortHeader
                            label="Size"
                            field="size_bytes"
                            currentField={
                              sortField
                            }
                            descending={
                              descending
                            }
                            onSort={
                              sort
                            }
                          />
                        </th>
                      </tr>
                    </thead>

                    <tbody>
                      {
                        files.map(
                          (
                            file
                          ) => (
                            <tr
                              key={
                                file.id
                              }
                              onClick={
                                () =>
                                  setSelectedMediaItemId(
                                    file.media_item
                                  )
                              }
                              className="
                                cursor-pointer
                                border-b
                                hover:bg-muted/50
                              "
                            >
                              <td
                                className="
                                  p-3
                                "
                              >
                                <div
                                  className="
                                    font-medium
                                  "
                                >
                                  {
                                    file.title
                                  }
                                </div>

                                <div
                                  className="
                                    max-w-[440px]
                                    truncate
                                    text-xs
                                    text-muted-foreground
                                  "
                                >
                                  {
                                    file.relative_path
                                  }
                                </div>
                              </td>

                              {
                                library.content_type
                                === "online_video"
                                && (
                                  <td
                                    className="
                                      p-3
                                    "
                                  >
                                    {
                                      file.channel_title
                                      || "—"
                                    }
                                  </td>
                                )
                              }

                              <td
                                className="
                                  p-3
                                "
                              >
                                {
                                  file.video_codec
                                  || "—"
                                }
                              </td>

                              <td
                                className="
                                  p-3
                                "
                              >
                                {
                                  file.width
                                  && file.height
                                    ? `${file.width}×${file.height}`
                                    : "—"
                                }
                              </td>

                              <td
                                className="
                                  p-3
                                  tabular-nums
                                "
                              >
                                {
                                  formatDuration(
                                    file.duration_seconds
                                  )
                                }
                              </td>

                              <td
                                className="
                                  p-3
                                  tabular-nums
                                "
                              >
                                {
                                  formatBytes(
                                    file.size_bytes
                                  )
                                }
                              </td>
                            </tr>
                          )
                        )
                      }
                    </tbody>
                  </table>
                </div>

                <TablePagination
                  page={page}
                  pageSize={
                    pageSize
                  }
                  totalPages={
                    totalPages
                  }
                  count={count}
                  onPageChange={
                    setPage
                  }
                  onPageSizeChange={
                    handlePageSizeChange
                  }
                />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>

      <MediaDetailDialog
        mediaItemId={
          selectedMediaItemId
        }
        onClose={
          () =>
            setSelectedMediaItemId(
              null
            )
        }
      />
    </>
  )
}
