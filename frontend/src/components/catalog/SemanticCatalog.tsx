import {
  useCallback,
  useEffect,
  useState,
} from "react"

import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
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
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import {
  Dialog,
  DialogTitle,
} from "@/components/ui/dialog"

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
  ScrollableDialogBody,
  ScrollableDialogContent,
  ScrollableDialogHeader,
} from "@/components/dialogs/ScrollableDialog"

import {
  MediaDetailDialog,
} from "@/components/media/MediaDetailDialog"

import {
  TablePagination,
} from "@/components/tables/TablePagination"

import {
  getCatalogEpisodes,
  getCatalogMovies,
  getCatalogSeasons,
  getCatalogSeries,
  getSemanticMatches,
} from "@/lib/api"

import {
  formatBytes,
  formatDuration,
} from "@/lib/format"

import type {
  CatalogEpisode,
  CatalogMovie,
  CatalogSeason,
  CatalogSeries,
  Library,
  PageSize,
} from "@/types"


type CatalogKind =
  | "movies"
  | "tv"


function SortButton({
  label,
  active,
  descending,
  onClick,
}: {
  label: string
  active: boolean
  descending: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={
        onClick
      }
      className="
        inline-flex
        items-center
        gap-1
        font-medium
      "
    >
      {label}

      {
        !active
          ? (
            <ArrowUpDown
              className="
                h-3.5
                w-3.5
              "
            />
          )
          : descending
            ? (
              <ArrowDown
                className="
                  h-3.5
                  w-3.5
                "
              />
            )
            : (
              <ArrowUp
                className="
                  h-3.5
                  w-3.5
                "
              />
            )
      }
    </button>
  )
}


function MovieCatalog({
  library,
  refreshKey,
}: {
  library: Library
  refreshKey: string
}) {
  const [
    movies,
    setMovies,
  ] = useState<
    CatalogMovie[]
  >([])

  const [
    count,
    setCount,
  ] = useState(0)

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
    search,
    setSearch,
  ] = useState("")

  const [
    descending,
    setDescending,
  ] = useState(false)

  const [
    selectedMovie,
    setSelectedMovie,
  ] = useState<
    CatalogMovie | null
  >(null)


  const load =
    useCallback(
      async () => {
        const result =
          await getCatalogMovies(
            library.id,
            search,
            descending
              ? "-title"
              : "title",
            page,
            pageSize,
          )

        setMovies(
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
        search,
        descending,
        page,
        pageSize,
        refreshKey,
      ],
    )


  useEffect(
    () => {
      void load()
    },
    [
      load,
    ],
  )


  return (
    <>
      <div
        className="
          space-y-4
        "
      >
        <Input
          value={search}
          onChange={
            (
              event
            ) => {
              setSearch(
                event
                  .target
                  .value
              )

              setPage(1)
            }
          }
          placeholder="Search movies..."
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
                  <SortButton
                    label="Title"
                    active
                    descending={
                      descending
                    }
                    onClick={
                      () => {
                        setDescending(
                          !descending
                        )

                        setPage(1)
                      }
                    }
                  />
                </th>

                <th
                  className="
                    p-3
                  "
                >
                  Year
                </th>

                <th
                  className="
                    p-3
                  "
                >
                  Runtime
                </th>

                <th
                  className="
                    p-3
                  "
                >
                  Versions
                </th>

                <th
                  className="
                    p-3
                  "
                >
                  Storage
                </th>
              </tr>
            </thead>

            <tbody>
              {
                movies.map(
                  (
                    movie
                  ) => (
                    <tr
                      key={
                        movie.id
                      }
                      onClick={
                        () =>
                          setSelectedMovie(
                            movie
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
                          font-medium
                        "
                      >
                        {
                          movie.title
                        }
                      </td>

                      <td
                        className="
                          p-3
                          tabular-nums
                        "
                      >
                        {
                          movie.year
                          ?? "—"
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
                            movie
                              .runtime_seconds
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
                          movie
                            .version_count
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
                            movie
                              .storage_bytes
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
            (
              value
            ) => {
              setPageSize(
                value
              )

              setPage(1)
            }
          }
        />
      </div>

      <Dialog
        open={
          selectedMovie
          !== null
        }
        onOpenChange={
          (
            open
          ) => {
            if (!open) {
              setSelectedMovie(
                null
              )
            }
          }
        }
      >
        <ScrollableDialogContent>
          {
            selectedMovie
            && (
              <>
                <ScrollableDialogHeader>
                  <DialogTitle>
                    {
                      selectedMovie
                        .title
                    }

                    {
                      selectedMovie.year
                      ? (
                        ` (${selectedMovie.year})`
                      )
                      : ""
                    }
                  </DialogTitle>
                </ScrollableDialogHeader>

                <ScrollableDialogBody
                  className="
                    space-y-5
                  "
                >
                  <div
                    className="
                      grid
                      gap-4
                      md:grid-cols-3
                    "
                  >
                    <Card>
                      <CardHeader>
                        <CardDescription>
                          Runtime
                        </CardDescription>

                        <CardTitle
                          className="
                            text-xl
                          "
                        >
                          {
                            formatDuration(
                              selectedMovie
                                .runtime_seconds
                            )
                          }
                        </CardTitle>
                      </CardHeader>
                    </Card>

                    <Card>
                      <CardHeader>
                        <CardDescription>
                          Versions
                        </CardDescription>

                        <CardTitle
                          className="
                            text-xl
                          "
                        >
                          {
                            selectedMovie
                              .version_count
                          }
                        </CardTitle>
                      </CardHeader>
                    </Card>

                    <Card>
                      <CardHeader>
                        <CardDescription>
                          Storage
                        </CardDescription>

                        <CardTitle
                          className="
                            text-xl
                          "
                        >
                          {
                            formatBytes(
                              selectedMovie
                                .storage_bytes
                            )
                          }
                        </CardTitle>
                      </CardHeader>
                    </Card>
                  </div>

                  <div
                    className="
                      space-y-3
                    "
                  >
                    <h3
                      className="
                        text-lg
                        font-semibold
                      "
                    >
                      Versions
                    </h3>

                    {
                      selectedMovie
                        .versions
                        .map(
                          (
                            version
                          ) => (
                            <div
                              key={
                                version.id
                              }
                              className="
                                rounded-md
                                border
                                p-4
                              "
                            >
                              <div
                                className="
                                  flex
                                  flex-wrap
                                  items-center
                                  gap-2
                                "
                              >
                                <strong>
                                  {
                                    version.name
                                  }
                                </strong>

                                {
                                  version.edition
                                  && (
                                    <Badge
                                      variant="outline"
                                    >
                                      {
                                        version.edition
                                      }
                                    </Badge>
                                  )
                                }

                                {
                                  version.is_primary
                                  && (
                                    <Badge>
                                      Primary
                                    </Badge>
                                  )
                                }
                              </div>

                              <div
                                className="
                                  mt-2
                                  break-all
                                  text-sm
                                  text-muted-foreground
                                "
                              >
                                {
                                  version
                                    .relative_path
                                }
                              </div>

                              <div
                                className="
                                  mt-2
                                  flex
                                  flex-wrap
                                  gap-4
                                  text-sm
                                "
                              >
                                <span>
                                  {
                                    formatBytes(
                                      version
                                        .size_bytes
                                    )
                                  }
                                </span>

                                <span>
                                  {
                                    formatDuration(
                                      version
                                        .duration_seconds
                                    )
                                  }
                                </span>

                                <span>
                                  {
                                    version
                                      .video_codec
                                    || "—"
                                  }
                                </span>

                                <span>
                                  {
                                    version.width
                                    && version.height
                                      ? (
                                        `${version.width}×`
                                        + `${version.height}`
                                      )
                                      : "—"
                                  }
                                </span>
                              </div>
                            </div>
                          )
                        )
                    }
                  </div>
                </ScrollableDialogBody>
              </>
            )
          }
        </ScrollableDialogContent>
      </Dialog>
    </>
  )
}


function TvCatalog({
  library,
  refreshKey,
}: {
  library: Library
  refreshKey: string
}) {
  const [
    series,
    setSeries,
  ] = useState<
    CatalogSeries[]
  >([])

  const [
    selectedSeries,
    setSelectedSeries,
  ] = useState<
    CatalogSeries | null
  >(null)

  const [
    seasons,
    setSeasons,
  ] = useState<
    CatalogSeason[]
  >([])

  const [
    selectedSeason,
    setSelectedSeason,
  ] = useState<
    CatalogSeason | null
  >(null)

  const [
    episodes,
    setEpisodes,
  ] = useState<
    CatalogEpisode[]
  >([])

  const [
    selectedMediaItemId,
    setSelectedMediaItemId,
  ] = useState<
    string | null
  >(null)

  const [
    search,
    setSearch,
  ] = useState("")

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
    count,
    setCount,
  ] = useState(0)

  const [
    totalPages,
    setTotalPages,
  ] = useState(1)

  const [
    descending,
    setDescending,
  ] = useState(false)


  const loadSeries =
    useCallback(
      async () => {
        const result =
          await getCatalogSeries(
            library.id,
            search,
            descending
              ? "-sort_title"
              : "sort_title",
            page,
            pageSize,
          )

        setSeries(
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
        search,
        descending,
        page,
        pageSize,
        refreshKey,
      ],
    )


  useEffect(
    () => {
      if (
        !selectedSeries
        && !selectedSeason
      ) {
        void loadSeries()
      }
    },
    [
      selectedSeries,
      selectedSeason,
      loadSeries,
    ],
  )


  useEffect(
    () => {
      if (!selectedSeries) {
        setSeasons([])
        return
      }

      void getCatalogSeasons(
        selectedSeries.id,
      ).then(
        (
          result
        ) =>
          setSeasons(
            result.results
          )
      )
    },
    [
      selectedSeries,
    ],
  )


  useEffect(
    () => {
      if (!selectedSeason) {
        setEpisodes([])
        return
      }

      void getCatalogEpisodes(
        selectedSeason.id,
        search,
        "episode_number",
        page,
        pageSize,
      ).then(
        (
          result
        ) => {
          setEpisodes(
            result.results
          )

          setCount(
            result.count
          )

          setTotalPages(
            result.total_pages
          )
        }
      )
    },
    [
      selectedSeason,
      search,
      page,
      pageSize,
    ],
  )


  function goSeriesRoot() {
    setSelectedSeries(
      null
    )

    setSelectedSeason(
      null
    )

    setSearch("")
    setPage(1)
  }


  function openSeries(
    item: CatalogSeries,
  ) {
    setSelectedSeries(
      item
    )

    setSelectedSeason(
      null
    )

    setSearch("")
    setPage(1)
  }


  function openSeason(
    item: CatalogSeason,
  ) {
    setSelectedSeason(
      item
    )

    setSearch("")
    setPage(1)
  }


  return (
    <>
      <div
        className="
          space-y-4
        "
      >
        <div
          className="
            flex
            flex-wrap
            items-center
            gap-2
            rounded-md
            border
            bg-muted/30
            p-2
          "
        >
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={
              goSeriesRoot
            }
          >
            TV Shows
          </Button>

          {
            selectedSeries
            && (
              <>
                <span
                  className="
                    text-muted-foreground
                  "
                >
                  /
                </span>

                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={
                    () => {
                      setSelectedSeason(
                        null
                      )

                      setSearch("")
                      setPage(1)
                    }
                  }
                >
                  {
                    selectedSeries
                      .title
                  }
                </Button>
              </>
            )
          }

          {
            selectedSeason
            && (
              <>
                <span
                  className="
                    text-muted-foreground
                  "
                >
                  /
                </span>

                <span
                  className="
                    px-2
                    text-sm
                    font-medium
                  "
                >
                  {
                    selectedSeason
                      .title
                  }
                </span>
              </>
            )
          }
        </div>

        {
          (
            !selectedSeries
            || selectedSeason
          )
          && (
            <Input
              value={search}
              onChange={
                (
                  event
                ) => {
                  setSearch(
                    event
                      .target
                      .value
                  )

                  setPage(1)
                }
              }
              placeholder={
                selectedSeason
                  ? "Search episodes..."
                  : "Search TV shows..."
              }
            />
          )
        }

        {
          !selectedSeries
          && (
            <>
              <div
                className="
                  overflow-x-auto
                "
              >
                <table
                  className="
                    w-full
                    min-w-[800px]
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
                        <SortButton
                          label="Series"
                          active
                          descending={
                            descending
                          }
                          onClick={
                            () => {
                              setDescending(
                                !descending
                              )

                              setPage(1)
                            }
                          }
                        />
                      </th>

                      <th
                        className="
                          p-3
                        "
                      >
                        Seasons
                      </th>

                      <th
                        className="
                          p-3
                        "
                      >
                        Episodes
                      </th>

                      <th
                        className="
                          p-3
                        "
                      >
                        Runtime
                      </th>

                      <th
                        className="
                          p-3
                        "
                      >
                        Storage
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {
                      series.map(
                        (
                          item
                        ) => (
                          <tr
                            key={
                              item.id
                            }
                            onClick={
                              () =>
                                openSeries(
                                  item
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
                                  item.title
                                }
                              </div>

                              {
                                item.start_year
                                && (
                                  <div
                                    className="
                                      text-xs
                                      text-muted-foreground
                                    "
                                  >
                                    {
                                      item.start_year
                                    }
                                  </div>
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
                                item
                                  .season_count
                              }
                            </td>

                            <td
                              className="
                                p-3
                                tabular-nums
                              "
                            >
                              {
                                item
                                  .episode_count
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
                                  item
                                    .runtime_seconds
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
                                  item
                                    .storage_bytes
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
                  (
                    value
                  ) => {
                    setPageSize(
                      value
                    )

                    setPage(1)
                  }
                }
              />
            </>
          )
        }

        {
          selectedSeries
          && !selectedSeason
          && (
            <div
              className="
                overflow-x-auto
              "
            >
              <table
                className="
                  w-full
                  min-w-[720px]
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
                      Season
                    </th>

                    <th
                      className="
                        p-3
                      "
                    >
                      Episodes
                    </th>

                    <th
                      className="
                        p-3
                      "
                    >
                      Runtime
                    </th>

                    <th
                      className="
                        p-3
                      "
                    >
                      Storage
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {
                    seasons.map(
                      (
                        season
                      ) => (
                        <tr
                          key={
                            season.id
                          }
                          onClick={
                            () =>
                              openSeason(
                                season
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
                              font-medium
                            "
                          >
                            {
                              season.title
                            }
                          </td>

                          <td
                            className="
                              p-3
                              tabular-nums
                            "
                          >
                            {
                              season
                                .episode_count
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
                                season
                                  .runtime_seconds
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
                                season
                                  .storage_bytes
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
          )
        }

        {
          selectedSeason
          && (
            <>
              <div
                className="
                  overflow-x-auto
                "
              >
                <table
                  className="
                    w-full
                    min-w-[820px]
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
                        #
                      </th>

                      <th
                        className="
                          p-3
                        "
                      >
                        Title
                      </th>

                      <th
                        className="
                          p-3
                        "
                      >
                        Runtime
                      </th>

                      <th
                        className="
                          p-3
                        "
                      >
                        Versions
                      </th>

                      <th
                        className="
                          p-3
                        "
                      >
                        Storage
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {
                      episodes.map(
                        (
                          episode
                        ) => (
                          <tr
                            key={
                              episode.id
                            }
                            onClick={
                              () =>
                                setSelectedMediaItemId(
                                  episode
                                    .media_item_id
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
                                tabular-nums
                              "
                            >
                              {
                                episode
                                  .episode_end_number
                                  ? (
                                    `${episode.episode_number}`
                                    + `–${episode.episode_end_number}`
                                  )
                                  : episode
                                      .episode_number
                              }
                            </td>

                            <td
                              className="
                                p-3
                                font-medium
                              "
                            >
                              {
                                episode.title
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
                                  episode
                                    .runtime_seconds
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
                                episode
                                  .version_count
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
                                  episode
                                    .storage_bytes
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
                  (
                    value
                  ) => {
                    setPageSize(
                      value
                    )

                    setPage(1)
                  }
                }
              />
            </>
          )
        }
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


export function SemanticCatalog({
  library,
}: {
  library: Library
}) {
  const refreshKey = (
    library.last_scanned_at
    ?? ""
  )
  const [
    unresolvedCount,
    setUnresolvedCount,
  ] = useState(0)

  const [
    conflictCount,
    setConflictCount,
  ] = useState(0)

  const defaultKind:
    CatalogKind = (
      library.content_type
      === "tv"
        ? "tv"
        : "movies"
    )

  const [
    kind,
    setKind,
  ] = useState<
    CatalogKind
  >(
    defaultKind
  )


  useEffect(
    () => {
      void Promise.all([
        getSemanticMatches(
          library.id,
          "unresolved",
          1,
          10,
        ),

        getSemanticMatches(
          library.id,
          "conflict",
          1,
          10,
        ),
      ]).then(
        ([
          unresolved,
          conflicts,
        ]) => {
          setUnresolvedCount(
            unresolved.count
          )

          setConflictCount(
            conflicts.count
          )
        }
      )
    },
    [
      library.id,
      refreshKey,
    ],
  )


  if (
    library.content_type
    === "online_video"
    || library.content_type
    === "generic"
  ) {
    return (
      <div
        className="
          rounded-md
          border
          p-6
          text-sm
          text-muted-foreground
        "
      >
        Semantic Movie/TV catalog matching is
        disabled for this library type. Use
        Folders, All Media, or change the library
        content type when appropriate.
      </div>
    )
  }


  const showChooser = (
    library.content_type
    === "auto"
    || library.content_type
    === "mixed"
  )


  return (
    <div
      className="
        space-y-4
      "
    >
      <div
        className="
          flex
          flex-wrap
          items-center
          justify-between
          gap-3
        "
      >
        <div
          className="
            flex
            flex-wrap
            gap-2
          "
        >
          {
            unresolvedCount
            > 0
            && (
              <Badge
                variant="outline"
              >
                {
                  unresolvedCount
                }
                {" unresolved"}
              </Badge>
            )
          }

          {
            conflictCount
            > 0
            && (
              <Badge
                variant="destructive"
              >
                {
                  conflictCount
                }
                {" conflicts"}
              </Badge>
            )
          }
        </div>
      </div>

      {
        showChooser
        ? (
          <Tabs
            value={kind}
            onValueChange={
              (
                value
              ) =>
                setKind(
                  (
                    value
                  ) as CatalogKind
                )
            }
          >
            <TabsList>
              <TabsTrigger
                value="movies"
              >
                Movies
              </TabsTrigger>

              <TabsTrigger
                value="tv"
              >
                TV Shows
              </TabsTrigger>
            </TabsList>

            <TabsContent
              value="movies"
              className="
                mt-5
              "
            >
              <MovieCatalog
                library={
                  library
                }
                refreshKey={
                  refreshKey
                }
              />
            </TabsContent>

            <TabsContent
              value="tv"
              className="
                mt-5
              "
            >
              <TvCatalog
                library={
                  library
                }
                refreshKey={
                  refreshKey
                }
              />
            </TabsContent>
          </Tabs>
        )
        : library.content_type
          === "tv"
          ? (
            <TvCatalog
              library={
                library
              }
              refreshKey={
                refreshKey
              }
            />
          )
          : (
            <MovieCatalog
              library={
                library
              }
              refreshKey={
                refreshKey
              }
            />
          )
      }
    </div>
  )
}
