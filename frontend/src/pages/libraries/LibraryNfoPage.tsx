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
  useSearchParams,
} from "react-router-dom"

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
  ScrollableDialogBody,
  ScrollableDialogContent,
  ScrollableDialogHeader,
} from "@/components/dialogs/ScrollableDialog"

import {
  FolderBrowser,
} from "@/components/library-browser/FolderBrowser"

import {
  Input,
} from "@/components/ui/input"

import {
  Label,
} from "@/components/ui/label"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"

import {
  TablePagination,
} from "@/components/tables/TablePagination"

import {
  getNfoFile,
  getNfoFiles,
  updateNfoFile,
  validateNfo,
} from "@/lib/api"

import {
  formatBytes,
  managementModeLabel,
} from "@/lib/format"

import {
  useLibraryOutlet,
} from "@/lib/route-context"

import type {
  NfoFile,
  NfoValidation,
  PageSize,
} from "@/types"


type NfoView =
  | "folders"
  | "all"

type NfoSort =
  | "relative_path"
  | "media_item__title"
  | "year"
  | "parse_status"
  | "size_bytes"


function NfoSortButton({
  label,
  field,
  sortField,
  descending,
  onSort,
}: {
  label: string
  field: NfoSort
  sortField: NfoSort
  descending: boolean

  onSort:
    (
      field: NfoSort
    ) => void
}) {
  const active =
    field === sortField

  return (
    <button
      type="button"
      onClick={
        () =>
          onSort(field)
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


export function LibraryNfoPage() {
  const {
    library,
  } = useLibraryOutlet()

  const [
    searchParams,
    setSearchParams,
  ] = useSearchParams()

  const view: NfoView =
    searchParams.get(
      "view"
    ) === "all"
      ? "all"
      : "folders"

  const folderPath =
    searchParams.get(
      "folder"
    )
    ?? ""

  const [
    nfos,
    setNfos,
  ] = useState<
    NfoFile[]
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
    sortField,
    setSortField,
  ] = useState<
    NfoSort
  >(
    "relative_path"
  )

  const [
    descending,
    setDescending,
  ] = useState(false)

  const [
    browserRefreshKey,
    setBrowserRefreshKey,
  ] = useState(0)

  const [
    selected,
    setSelected,
  ] = useState<
    NfoFile | null
  >(null)

  const [
    editor,
    setEditor,
  ] = useState("")

  const [
    validation,
    setValidation,
  ] = useState<
    NfoValidation | null
  >(null)

  const [
    message,
    setMessage,
  ] = useState<
    string | null
  >(null)

  const ordering =
    descending
      ? `-${sortField}`
      : sortField


  const loadFlat =
    useCallback(
      async () => {
        const result =
          await getNfoFiles(
            library.id,
            ordering,
            search,
            page,
            pageSize,
          )

        setNfos(
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
        void loadFlat()
      }
    },
    [
      view,
      loadFlat,
    ],
  )


  function setView(
    nextView: NfoView,
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
      === "all"
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


  function handlePageSizeChange(
    value: PageSize,
  ) {
    setPageSize(value)
    setPage(1)
  }


  function handleSort(
    field: NfoSort,
  ) {
    setPage(1)

    if (
      field
      === sortField
    ) {
      setDescending(
        !descending
      )

      return
    }

    setSortField(
      field
    )

    setDescending(
      false
    )
  }


  function open(
    nfo: NfoFile,
  ) {
    setSelected(nfo)
    setEditor(nfo.raw_xml)
    setValidation(null)
    setMessage(null)
  }


  async function openById(
    nfoId: string,
  ) {
    const nfo =
      await getNfoFile(
        nfoId
      )

    open(nfo)
  }


  async function handleValidate() {
    setValidation(
      await validateNfo(
        editor
      )
    )
  }


  async function handleSave() {
    if (!selected) {
      return
    }

    try {
      const updated =
        await updateNfoFile(
          selected.id,
          editor,
        )

      setSelected(updated)

      setEditor(
        updated.raw_xml
      )

      setMessage(
        "NFO saved."
      )

      setBrowserRefreshKey(
        (
          current
        ) =>
          current + 1
      )

      if (view === "all") {
        await loadFlat()
      }

    } catch (err) {
      setMessage(
        err instanceof Error
          ? err.message
          : "Unable to save NFO."
      )
    }
  }


  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>
            NFO
          </CardTitle>

          <CardDescription>
            Browse NFO files by their physical folder hierarchy or use the sortable flat list.
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
                  (
                    value
                  ) as NfoView
                )
            }
          >
            <TabsList>
              <TabsTrigger
                value="folders"
              >
                Folders
              </TabsTrigger>

              <TabsTrigger
                value="all"
              >
                All NFO
              </TabsTrigger>
            </TabsList>

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
                contentMode="nfo"
                refreshKey={
                  browserRefreshKey
                }
                onPathChange={
                  setFolderPath
                }
                onOpenNfo={
                  (
                    nfoId
                  ) =>
                    void openById(
                      nfoId
                    )
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
              <div
                className="
                  text-sm
                  text-muted-foreground
                "
              >
                {
                  count
                    .toLocaleString()
                }
                {" "}
                NFO files
              </div>

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
                placeholder="Search all NFO files..."
              />

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
                        <NfoSortButton
                          label="File"
                          field="relative_path"
                          sortField={
                            sortField
                          }
                          descending={
                            descending
                          }
                          onSort={
                            handleSort
                          }
                        />
                      </th>

                      <th
                        className="
                          p-3
                        "
                      >
                        <NfoSortButton
                          label="Media"
                          field="media_item__title"
                          sortField={
                            sortField
                          }
                          descending={
                            descending
                          }
                          onSort={
                            handleSort
                          }
                        />
                      </th>

                      <th
                        className="
                          p-3
                        "
                      >
                        <NfoSortButton
                          label="Year"
                          field="year"
                          sortField={
                            sortField
                          }
                          descending={
                            descending
                          }
                          onSort={
                            handleSort
                          }
                        />
                      </th>

                      <th
                        className="
                          p-3
                        "
                      >
                        <NfoSortButton
                          label="Status"
                          field="parse_status"
                          sortField={
                            sortField
                          }
                          descending={
                            descending
                          }
                          onSort={
                            handleSort
                          }
                        />
                      </th>

                      <th
                        className="
                          p-3
                        "
                      >
                        <NfoSortButton
                          label="Size"
                          field="size_bytes"
                          sortField={
                            sortField
                          }
                          descending={
                            descending
                          }
                          onSort={
                            handleSort
                          }
                        />
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {
                      nfos.map(
                        (
                          nfo
                        ) => (
                          <tr
                            key={
                              nfo.id
                            }
                            onClick={
                              () =>
                                open(nfo)
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
                                  nfo.file_name
                                }
                              </div>

                              <div
                                className="
                                  max-w-[480px]
                                  truncate
                                  text-xs
                                  text-muted-foreground
                                "
                                title={
                                  nfo.relative_path
                                }
                              >
                                {
                                  nfo.relative_path
                                }
                              </div>
                            </td>

                            <td
                              className="
                                p-3
                              "
                            >
                              {
                                nfo.media_title
                                ?? "Orphaned"
                              }
                            </td>

                            <td
                              className="
                                p-3
                                tabular-nums
                              "
                            >
                              {
                                nfo.year
                                ?? "—"
                              }
                            </td>

                            <td
                              className="
                                p-3
                              "
                            >
                              <Badge
                                variant={
                                  nfo.parse_status
                                  === "ok"
                                    ? "secondary"
                                    : nfo.parse_status
                                      === "error"
                                      ? "destructive"
                                      : "outline"
                                }
                              >
                                {
                                  nfo.parse_status
                                }
                              </Badge>
                            </td>

                            <td
                              className="
                                p-3
                                tabular-nums
                              "
                            >
                              {
                                formatBytes(
                                  nfo.size_bytes
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

      <Dialog
        open={
          selected
          !== null
        }
        onOpenChange={
          (
            openDialog
          ) => {
            if (!openDialog) {
              setSelected(null)
              setValidation(null)
              setMessage(null)
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
          {selected && (
            <>
              <ScrollableDialogHeader>
                <DialogTitle>
                  {
                    selected.file_name
                  }
                </DialogTitle>
              </ScrollableDialogHeader>

              <ScrollableDialogBody
                className="
                  overflow-hidden
                "
              >
                <div
                  className="
                    grid
                    h-full
                    min-h-0
                    min-w-0
                    gap-6
                    lg:grid-cols-[320px_minmax(0,1fr)]
                  "
                >
                  <div
                    className="
                      min-h-0
                      min-w-0
                      space-y-4
                      overflow-y-auto
                      pr-1
                    "
                  >
                    <Card>
                      <CardHeader>
                        <CardTitle
                          className="
                            text-base
                          "
                        >
                          Structured
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
                            Title
                          </div>

                          <div>
                            {
                              selected.title
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
                              selected.year
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
                            Media
                          </div>

                          <div>
                            {
                              selected.media_title
                              ?? "Orphaned"
                            }
                          </div>
                        </div>

                        <div>
                          <div
                            className="
                              text-muted-foreground
                            "
                          >
                            Root
                          </div>

                          <div>
                            {
                              selected.root_element
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
                            Size
                          </div>

                          <div>
                            {
                              formatBytes(
                                selected.size_bytes
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
                            Mode
                          </div>

                          <div>
                            {
                              managementModeLabel(
                                selected
                                  .management_mode
                              )
                            }
                          </div>
                        </div>
                      </CardContent>
                    </Card>

                    {validation && (
                      <Card>
                        <CardHeader>
                          <CardTitle
                            className="
                              text-base
                            "
                          >
                            Validation
                          </CardTitle>
                        </CardHeader>

                        <CardContent
                          className="
                            space-y-2
                            text-sm
                          "
                        >
                          <Badge
                            variant={
                              validation.valid
                                ? "secondary"
                                : "destructive"
                            }
                          >
                            {
                              validation.valid
                                ? "Valid"
                                : "Invalid"
                            }
                          </Badge>

                          {
                            validation.error
                            && (
                              <div
                                className="
                                  text-destructive
                                "
                              >
                                {
                                  validation.error
                                }
                              </div>
                            )
                          }
                        </CardContent>
                      </Card>
                    )}
                  </div>

                  <div
                    className="
                      flex
                      min-h-0
                      min-w-0
                      flex-col
                      space-y-3
                    "
                  >
                    <Label>
                      NFO Content
                    </Label>

                    <textarea
                      value={editor}
                      onChange={
                        (
                          event
                        ) =>
                          setEditor(
                            event
                              .target
                              .value
                          )
                      }
                      className="
                        min-h-0
                        min-w-0
                        flex-1
                        resize-none
                        overflow-auto
                        rounded-md
                        border
                        bg-background
                        p-3
                        font-mono
                        text-sm
                      "
                    />

                    <div
                      className="
                        flex
                        gap-2
                      "
                    >
                      <Button
                        type="button"
                        variant="outline"
                        onClick={
                          handleValidate
                        }
                      >
                        Validate
                      </Button>

                      <Button
                        type="button"
                        onClick={
                          handleSave
                        }
                        disabled={
                          selected
                            .management_mode
                          === "read_only"
                        }
                      >
                        Save
                      </Button>
                    </div>

                    {message && (
                      <p
                        className="
                          text-sm
                        "
                      >
                        {message}
                      </p>
                    )}
                  </div>
                </div>
              </ScrollableDialogBody>
            </>
          )}
        </ScrollableDialogContent>
      </Dialog>
    </>
  )
}
