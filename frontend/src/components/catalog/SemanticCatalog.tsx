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
  Input,
} from "@/components/ui/input"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"

import {
  CatalogItemEditorDialog,
} from "@/components/catalog/CatalogItemEditorDialog"

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
  CatalogEditorKind,
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
      onClick={onClick}
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
              className="h-3.5 w-3.5"
            />
          )
          : descending
            ? (
              <ArrowDown
                className="h-3.5 w-3.5"
              />
            )
            : (
              <ArrowUp
                className="h-3.5 w-3.5"
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
  ] = useState<CatalogMovie[]>([])

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
  ] = useState<PageSize>(20)

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
    editorId,
    setEditorId,
  ] = useState<string | null>(null)


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

        setMovies(result.results)
        setCount(result.count)
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
    [load],
  )


  return (
    <>
      <div
        className="space-y-4"
      >
        <Input
          value={search}
          onChange={
            event => {
              setSearch(
                event.target.value
              )
              setPage(1)
            }
          }
          placeholder="Search movies..."
        />

        <div
          className="overflow-x-auto"
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
                <th className="p-3">
                  <SortButton
                    label="Title"
                    active
                    descending={descending}
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
                <th className="p-3">
                  Year
                </th>
                <th className="p-3">
                  Runtime
                </th>
                <th className="p-3">
                  Versions
                </th>
                <th className="p-3">
                  Storage
                </th>
                <th
                  className="p-3 text-right"
                >
                  Action
                </th>
              </tr>
            </thead>

            <tbody>
              {
                movies.map(
                  movie => (
                    <tr
                      key={movie.id}
                      className="
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
                        {movie.title}
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
                            movie.runtime_seconds
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
                          movie.version_count
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
                            movie.storage_bytes
                          )
                        }
                      </td>
                      <td
                        className="
                          p-3
                          text-right
                        "
                      >
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={
                            () =>
                              setEditorId(
                                movie.id
                              )
                          }
                        >
                          Open
                        </Button>
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
          pageSize={pageSize}
          totalPages={totalPages}
          count={count}
          onPageChange={setPage}
          onPageSizeChange={
            value => {
              setPageSize(value)
              setPage(1)
            }
          }
        />
      </div>

      <CatalogItemEditorDialog
        kind={
          editorId
            ? "movie"
            : null
        }
        id={editorId}
        onClose={
          () => setEditorId(null)
        }
        onChanged={load}
      />
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
  ] = useState<CatalogSeries[]>([])

  const [
    selectedSeries,
    setSelectedSeries,
  ] = useState<CatalogSeries | null>(null)

  const [
    seasons,
    setSeasons,
  ] = useState<CatalogSeason[]>([])

  const [
    selectedSeason,
    setSelectedSeason,
  ] = useState<CatalogSeason | null>(null)

  const [
    episodes,
    setEpisodes,
  ] = useState<CatalogEpisode[]>([])

  const [
    editorKind,
    setEditorKind,
  ] = useState<CatalogEditorKind | null>(null)

  const [
    editorId,
    setEditorId,
  ] = useState<string | null>(null)

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
  ] = useState<PageSize>(20)

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

        setSeries(result.results)
        setCount(result.count)
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


  const loadSeasons =
    useCallback(
      async () => {
        if (!selectedSeries) {
          setSeasons([])
          return
        }

        const result =
          await getCatalogSeasons(
            selectedSeries.id,
          )

        setSeasons(
          result.results
        )
      },
      [selectedSeries],
    )


  const loadEpisodes =
    useCallback(
      async () => {
        if (!selectedSeason) {
          setEpisodes([])
          return
        }

        const result =
          await getCatalogEpisodes(
            selectedSeason.id,
            search,
            "episode_number",
            page,
            pageSize,
          )

        setEpisodes(result.results)
        setCount(result.count)
        setTotalPages(
          result.total_pages
        )
      },
      [
        selectedSeason,
        search,
        page,
        pageSize,
      ],
    )


  useEffect(
    () => {
      if (!selectedSeries) {
        void loadSeries()
      }
    },
    [
      selectedSeries,
      loadSeries,
    ],
  )


  useEffect(
    () => {
      void loadSeasons()
    },
    [loadSeasons],
  )


  useEffect(
    () => {
      void loadEpisodes()
    },
    [loadEpisodes],
  )


  function goRoot() {
    setSelectedSeries(null)
    setSelectedSeason(null)
    setSearch("")
    setPage(1)
  }


  function openSeries(
    item: CatalogSeries,
  ) {
    setSelectedSeries(item)
    setSelectedSeason(null)
    setSearch("")
    setPage(1)
  }


  function openSeason(
    item: CatalogSeason,
  ) {
    setSelectedSeason(item)
    setSearch("")
    setPage(1)
  }


  function openEditor(
    kind: CatalogEditorKind,
    id: string,
  ) {
    setEditorKind(kind)
    setEditorId(id)
  }


  async function refreshAfterEditor() {
    if (editorKind === "series") {
      await loadSeries()
      await loadSeasons()
      return
    }

    if (editorKind === "season") {
      await loadSeasons()
      await loadEpisodes()
      return
    }

    if (editorKind === "episode") {
      await loadEpisodes()
    }
  }


  return (
    <>
      <div
        className="space-y-4"
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
            onClick={goRoot}
          >
            TV Shows
          </Button>

          {
            selectedSeries
            && (
              <>
                <span
                  className="text-muted-foreground"
                >
                  /
                </span>

                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={
                    () => {
                      setSelectedSeason(null)
                      setSearch("")
                      setPage(1)
                    }
                  }
                >
                  {selectedSeries.title}
                </Button>
              </>
            )
          }

          {
            selectedSeason
            && (
              <>
                <span
                  className="text-muted-foreground"
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
                  {selectedSeason.title}
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
                event => {
                  setSearch(
                    event.target.value
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
                className="overflow-x-auto"
              >
                <table
                  className="
                    w-full
                    min-w-[900px]
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
                      <th className="p-3">
                        <SortButton
                          label="Series"
                          active
                          descending={descending}
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
                      <th className="p-3">
                        Seasons
                      </th>
                      <th className="p-3">
                        Episodes
                      </th>
                      <th className="p-3">
                        Runtime
                      </th>
                      <th className="p-3">
                        Storage
                      </th>
                      <th
                        className="p-3 text-right"
                      >
                        Metadata
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {
                      series.map(
                        item => (
                          <tr
                            key={item.id}
                            onClick={
                              () =>
                                openSeries(item)
                            }
                            className="
                              cursor-pointer
                              border-b
                              hover:bg-muted/50
                            "
                          >
                            <td className="p-3">
                              <div
                                className="font-medium"
                              >
                                {item.title}
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
                                    {item.start_year}
                                  </div>
                                )
                              }
                            </td>
                            <td
                              className="p-3 tabular-nums"
                            >
                              {item.season_count}
                            </td>
                            <td
                              className="p-3 tabular-nums"
                            >
                              {item.episode_count}
                            </td>
                            <td
                              className="p-3 tabular-nums"
                            >
                              {
                                formatDuration(
                                  item.runtime_seconds
                                )
                              }
                            </td>
                            <td
                              className="p-3 tabular-nums"
                            >
                              {
                                formatBytes(
                                  item.storage_bytes
                                )
                              }
                            </td>
                            <td
                              className="p-3 text-right"
                            >
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={
                                  event => {
                                    event.stopPropagation()
                                    openEditor(
                                      "series",
                                      item.id,
                                    )
                                  }
                                }
                              >
                                Edit
                              </Button>
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
                pageSize={pageSize}
                totalPages={totalPages}
                count={count}
                onPageChange={setPage}
                onPageSizeChange={
                  value => {
                    setPageSize(value)
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
              className="overflow-x-auto"
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
                    <th className="p-3">
                      Season
                    </th>
                    <th className="p-3">
                      Episodes
                    </th>
                    <th className="p-3">
                      Runtime
                    </th>
                    <th className="p-3">
                      Storage
                    </th>
                    <th
                      className="p-3 text-right"
                    >
                      Metadata
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {
                    seasons.map(
                      season => (
                        <tr
                          key={season.id}
                          onClick={
                            () =>
                              openSeason(season)
                          }
                          className="
                            cursor-pointer
                            border-b
                            hover:bg-muted/50
                          "
                        >
                          <td
                            className="p-3 font-medium"
                          >
                            {season.title}
                          </td>
                          <td
                            className="p-3 tabular-nums"
                          >
                            {season.episode_count}
                          </td>
                          <td
                            className="p-3 tabular-nums"
                          >
                            {
                              formatDuration(
                                season.runtime_seconds
                              )
                            }
                          </td>
                          <td
                            className="p-3 tabular-nums"
                          >
                            {
                              formatBytes(
                                season.storage_bytes
                              )
                            }
                          </td>
                          <td
                            className="p-3 text-right"
                          >
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={
                                event => {
                                  event.stopPropagation()
                                  openEditor(
                                    "season",
                                    season.id,
                                  )
                                }
                              }
                            >
                              Edit
                            </Button>
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
                className="overflow-x-auto"
              >
                <table
                  className="
                    w-full
                    min-w-[860px]
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
                      <th className="p-3">
                        #
                      </th>
                      <th className="p-3">
                        Title
                      </th>
                      <th className="p-3">
                        Runtime
                      </th>
                      <th className="p-3">
                        Versions
                      </th>
                      <th className="p-3">
                        Storage
                      </th>
                      <th
                        className="p-3 text-right"
                      >
                        Metadata
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {
                      episodes.map(
                        episode => (
                          <tr
                            key={episode.id}
                            className="
                              border-b
                              hover:bg-muted/50
                            "
                          >
                            <td
                              className="p-3 tabular-nums"
                            >
                              {
                                episode.episode_end_number
                                  ? (
                                    `${episode.episode_number}`
                                    + `–${episode.episode_end_number}`
                                  )
                                  : episode.episode_number
                              }
                            </td>
                            <td
                              className="p-3 font-medium"
                            >
                              {episode.title}
                            </td>
                            <td
                              className="p-3 tabular-nums"
                            >
                              {
                                formatDuration(
                                  episode.runtime_seconds
                                )
                              }
                            </td>
                            <td
                              className="p-3 tabular-nums"
                            >
                              {episode.version_count}
                            </td>
                            <td
                              className="p-3 tabular-nums"
                            >
                              {
                                formatBytes(
                                  episode.storage_bytes
                                )
                              }
                            </td>
                            <td
                              className="p-3 text-right"
                            >
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={
                                  () =>
                                    openEditor(
                                      "episode",
                                      episode.id,
                                    )
                                }
                              >
                                Open
                              </Button>
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
                pageSize={pageSize}
                totalPages={totalPages}
                count={count}
                onPageChange={setPage}
                onPageSizeChange={
                  value => {
                    setPageSize(value)
                    setPage(1)
                  }
                }
              />
            </>
          )
        }
      </div>

      <CatalogItemEditorDialog
        kind={editorKind}
        id={editorId}
        onClose={
          () => {
            setEditorKind(null)
            setEditorId(null)
          }
        }
        onChanged={
          refreshAfterEditor
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
  const refreshKey =
    library.last_scanned_at
    ?? ""

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
  ] = useState<CatalogKind>(
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
      className="space-y-4"
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
            unresolvedCount > 0
            && (
              <Badge
                variant="outline"
              >
                {unresolvedCount}
                {" unresolved"}
              </Badge>
            )
          }

          {
            conflictCount > 0
            && (
              <Badge
                variant="destructive"
              >
                {conflictCount}
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
                value =>
                  setKind(
                    value as CatalogKind
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
                className="mt-4"
              >
                <MovieCatalog
                  library={library}
                  refreshKey={refreshKey}
                />
              </TabsContent>

              <TabsContent
                value="tv"
                className="mt-4"
              >
                <TvCatalog
                  library={library}
                  refreshKey={refreshKey}
                />
              </TabsContent>
            </Tabs>
          )
          : library.content_type
            === "tv"
            ? (
              <TvCatalog
                library={library}
                refreshKey={refreshKey}
              />
            )
            : (
              <MovieCatalog
                library={library}
                refreshKey={refreshKey}
              />
            )
      }
    </div>
  )
}
