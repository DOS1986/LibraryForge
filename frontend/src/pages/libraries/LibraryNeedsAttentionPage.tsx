import {
  useCallback,
  useEffect,
  useState,
} from "react"

import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
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
  Input,
} from "@/components/ui/input"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"

import {
  SemanticMatchDialog,
} from "@/components/attention/SemanticMatchDialog"

import {
  TablePagination,
} from "@/components/tables/TablePagination"

import {
  getSemanticMatchPage,
} from "@/lib/api"

import {
  formatBytes,
  formatDuration,
} from "@/lib/format"

import {
  useLibraryOutlet,
} from "@/lib/route-context"

import type {
  PageSize,
  SemanticMatch,
} from "@/types"


type AttentionTab =
  | "unresolved"
  | "conflict"
  | "confirmed"


function currentAssignment(
  match: SemanticMatch,
) {
  const assignment =
    match.current_assignment

  if (!assignment) {
    return "—"
  }

  if (assignment.kind === "online_video") {
    const sourceId = assignment.source_id || "unknown"
    return (
      `${assignment.title || sourceId}`
      + (assignment.channel_title ? ` · ${assignment.channel_title}` : "")
    )
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
  )
}


export function LibraryNeedsAttentionPage() {
  const {
    library,
  } = useLibraryOutlet()

  const [
    tab,
    setTab,
  ] = useState<
    AttentionTab
  >(
    "unresolved"
  )

  const [
    matches,
    setMatches,
  ] = useState<
    SemanticMatch[]
  >([])

  const [
    selected,
    setSelected,
  ] = useState<
    SemanticMatch | null
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
    unresolvedCount,
    setUnresolvedCount,
  ] = useState(0)

  const [
    conflictCount,
    setConflictCount,
  ] = useState(0)

  const [
    confirmedCount,
    setConfirmedCount,
  ] = useState(0)

  const [
    loading,
    setLoading,
  ] = useState(false)

  const [
    error,
    setError,
  ] = useState<
    string | null
  >(null)


  const refreshCounts =
    useCallback(
      async () => {
        const [
          unresolved,
          conflicts,
          confirmed,
        ] = await Promise.all([
          getSemanticMatchPage(
            library.id,
            {
              status:
                "unresolved",

              page:
                1,

              pageSize:
                10,
            },
          ),

          getSemanticMatchPage(
            library.id,
            {
              status:
                "conflict",

              page:
                1,

              pageSize:
                10,
            },
          ),

          getSemanticMatchPage(
            library.id,
            {
              locked:
                true,

              page:
                1,

              pageSize:
                10,
            },
          ),
        ])

        setUnresolvedCount(
          unresolved.count
        )

        setConflictCount(
          conflicts.count
        )

        setConfirmedCount(
          confirmed.count
        )
      },
      [
        library.id,
      ],
    )


  const load =
    useCallback(
      async () => {
        setLoading(true)
        setError(null)

        try {
          const result =
            await getSemanticMatchPage(
              library.id,
              {
                status:
                  tab
                  === "confirmed"
                    ? undefined
                    : tab,

                locked:
                  tab
                  === "confirmed"
                    ? true
                    : undefined,

                search,

                ordering:
                  tab
                  === "confirmed"
                    ? "-updated_at"
                    : (
                      "-confidence"
                    ),

                page,

                pageSize,
              },
            )

          setMatches(
            result.results
          )

          setCount(
            result.count
          )

          setTotalPages(
            result.total_pages
          )

        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : (
                "Unable to load "
                + "semantic matches."
              )
          )

        } finally {
          setLoading(false)
        }
      },
      [
        library.id,
        tab,
        search,
        page,
        pageSize,
      ],
    )


  useEffect(
    () => {
      void Promise.all([
        load(),
        refreshCounts(),
      ])
    },
    [
      load,
      refreshCounts,
    ],
  )


  function changeTab(
    value: string,
  ) {
    setTab(
      (
        value
      ) as AttentionTab
    )

    setSearch("")
    setPage(1)
    setSelected(null)
  }


  async function handleChanged() {
    await Promise.all([
      load(),
      refreshCounts(),
    ])
  }


  const semanticDisabled = (
    library.content_type
    === "generic"
  )


  return (
    <>
      <div
        className="
          space-y-6
        "
      >
        <Card>
          <CardHeader>
            <CardTitle>
              Needs Attention
            </CardTitle>

            <CardDescription>
              Review files LibraryForge could not
              identify safely, resolve metadata
              conflicts, and inspect locked
              decisions.
            </CardDescription>
          </CardHeader>

          {
            semanticDisabled
            && (
              <CardContent>
                <div
                  className="
                    rounded-md
                    border
                    bg-muted/30
                    p-4
                    text-sm
                    text-muted-foreground
                  "
                >
                  Semantic matching is disabled for
                  this library's current Content Type. Existing
                  historical decisions can still
                  be reviewed here, but new scans
                  will not create semantic
                  attention items.
                </div>
              </CardContent>
            )
          }
        </Card>

        <Card>
          <CardContent
            className="
              pt-6
            "
          >
            <Tabs
              value={tab}
              onValueChange={
                changeTab
              }
            >
              <TabsList
                className="
                  grid
                  w-full
                  grid-cols-3
                  lg:w-[620px]
                "
              >
                <TabsTrigger
                  value="unresolved"
                  className="
                    gap-2
                  "
                >
                  <CircleHelp
                    className="
                      h-4
                      w-4
                    "
                  />

                  Unresolved

                  <Badge
                    variant="outline"
                  >
                    {
                      unresolvedCount
                    }
                  </Badge>
                </TabsTrigger>

                <TabsTrigger
                  value="conflict"
                  className="
                    gap-2
                  "
                >
                  <AlertTriangle
                    className="
                      h-4
                      w-4
                    "
                  />

                  Conflicts

                  <Badge
                    variant={
                      conflictCount
                      > 0
                        ? "destructive"
                        : "outline"
                    }
                  >
                    {
                      conflictCount
                    }
                  </Badge>
                </TabsTrigger>

                <TabsTrigger
                  value="confirmed"
                  className="
                    gap-2
                  "
                >
                  <CheckCircle2
                    className="
                      h-4
                      w-4
                    "
                  />

                  Confirmed

                  <Badge
                    variant="secondary"
                  >
                    {
                      confirmedCount
                    }
                  </Badge>
                </TabsTrigger>
              </TabsList>

              <TabsContent
                value={tab}
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
                    tab
                    === "confirmed"
                      ? (
                        "Search confirmed matches..."
                      )
                      : (
                        "Search files needing attention..."
                      )
                  }
                />

                {error && (
                  <div
                    className="
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
                )}

                <div
                  className="
                    overflow-x-auto
                    rounded-md
                    border
                  "
                >
                  <table
                    className="
                      w-full
                      min-w-[980px]
                      text-sm
                    "
                  >
                    <thead>
                      <tr
                        className="
                          border-b
                          bg-muted/40
                          text-left
                        "
                      >
                        <th
                          className="
                            p-3
                          "
                        >
                          File
                        </th>

                        <th
                          className="
                            p-3
                          "
                        >
                          Status
                        </th>

                        <th
                          className="
                            p-3
                          "
                        >
                          Source
                        </th>

                        <th
                          className="
                            p-3
                          "
                        >
                          Confidence
                        </th>

                        <th
                          className="
                            p-3
                          "
                        >
                          Current Assignment
                        </th>

                        <th
                          className="
                            p-3
                          "
                        >
                          Media
                        </th>

                        <th
                          className="
                            p-3
                            text-right
                          "
                        >
                          Action
                        </th>
                      </tr>
                    </thead>

                    <tbody>
                      {
                        loading
                        && matches.length
                        === 0
                        && (
                          <tr>
                            <td
                              colSpan={7}
                              className="
                                p-10
                                text-center
                                text-muted-foreground
                              "
                            >
                              Loading...
                            </td>
                          </tr>
                        )
                      }

                      {
                        !loading
                        && matches.length
                        === 0
                        && (
                          <tr>
                            <td
                              colSpan={7}
                              className="
                                p-10
                                text-center
                                text-muted-foreground
                              "
                            >
                              {
                                tab
                                === "confirmed"
                                  ? (
                                    "No locked semantic decisions."
                                  )
                                  : (
                                    "Nothing needs attention in this queue."
                                  )
                              }
                            </td>
                          </tr>
                        )
                      }

                      {
                        matches.map(
                          (
                            match
                          ) => (
                            <tr
                              key={
                                match.id
                              }
                              onClick={
                                () =>
                                  setSelected(
                                    match
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
                                  max-w-[360px]
                                  p-3
                                "
                              >
                                <div
                                  className="
                                    truncate
                                    font-medium
                                  "
                                  title={
                                    match.file_name
                                  }
                                >
                                  {
                                    match.file_name
                                  }
                                </div>

                                <div
                                  className="
                                    truncate
                                    text-xs
                                    text-muted-foreground
                                  "
                                  title={
                                    match.relative_path
                                  }
                                >
                                  {
                                    match.relative_path
                                  }
                                </div>
                              </td>

                              <td
                                className="
                                  p-3
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
                              </td>

                              <td
                                className="
                                  p-3
                                "
                              >
                                {
                                  match.source_label
                                  || "—"
                                }
                              </td>

                              <td
                                className="
                                  p-3
                                  tabular-nums
                                "
                              >
                                {
                                  `${Math.round(
                                    match.confidence
                                    * 100
                                  )}%`
                                }
                              </td>

                              <td
                                className="
                                  max-w-[280px]
                                  p-3
                                "
                              >
                                <div
                                  className="
                                    truncate
                                  "
                                  title={
                                    currentAssignment(
                                      match
                                    )
                                  }
                                >
                                  {
                                    currentAssignment(
                                      match
                                    )
                                  }
                                </div>
                              </td>

                              <td
                                className="
                                  p-3
                                  tabular-nums
                                "
                              >
                                <div>
                                  {
                                    formatDuration(
                                      match
                                        .duration_seconds
                                    )
                                  }
                                </div>

                                <div
                                  className="
                                    text-xs
                                    text-muted-foreground
                                  "
                                >
                                  {
                                    formatBytes(
                                      match
                                        .size_bytes
                                    )
                                  }
                                </div>
                              </td>

                              <td
                                className="
                                  p-3
                                  text-right
                                "
                              >
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  onClick={
                                    (
                                      event
                                    ) => {
                                      event
                                        .stopPropagation()

                                      setSelected(
                                        match
                                      )
                                    }
                                  }
                                >
                                  {
                                    tab
                                    === "confirmed"
                                      ? "Manage"
                                      : "Review"
                                  }
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
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>

      <SemanticMatchDialog
        library={
          library
        }
        match={
          selected
        }
        onClose={
          () =>
            setSelected(
              null
            )
        }
        onChanged={
          handleChanged
        }
      />
    </>
  )
}
