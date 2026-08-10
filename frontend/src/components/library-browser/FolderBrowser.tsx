import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react"

import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  FileImage,
  FileText,
  FileVideo2,
  Folder,
  Home,
} from "lucide-react"

import {
  Button,
} from "@/components/ui/button"

import {
  Input,
} from "@/components/ui/input"

import {
  TablePagination,
} from "@/components/tables/TablePagination"

import {
  getLibraryBrowser,
} from "@/lib/api"

import {
  formatBytes,
  formatDuration,
} from "@/lib/format"

import type {
  LibraryBrowserContentMode,
  LibraryBrowserEntry,
  LibraryBrowserResponse,
  LibraryBrowserSort,
  PageSize,
} from "@/types"


interface FolderBrowserProps {
  libraryId: string
  path: string
  contentMode:
    LibraryBrowserContentMode

  onPathChange:
    (
      path: string
    ) => void

  onOpenMedia?:
    (
      mediaItemId: string
    ) => void

  onOpenNfo?:
    (
      nfoId: string
    ) => void

  refreshKey?: number
}


function BrowserSortButton({
  label,
  field,
  sortField,
  descending,
  onSort,
}: {
  label: string
  field: LibraryBrowserSort
  sortField: LibraryBrowserSort
  descending: boolean

  onSort:
    (
      field: LibraryBrowserSort
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


export function FolderBrowser({
  libraryId,
  path,
  contentMode,
  onPathChange,
  onOpenMedia,
  onOpenNfo,
  refreshKey = 0,
}: FolderBrowserProps) {
  const [
    data,
    setData,
  ] = useState<
    LibraryBrowserResponse
    | null
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
    sortField,
    setSortField,
  ] = useState<
    LibraryBrowserSort
  >(
    "name"
  )

  const [
    descending,
    setDescending,
  ] = useState(false)

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


  const countSortField =
    useMemo<
      LibraryBrowserSort
    >(
      () => {
        if (
          contentMode
          === "nfo"
        ) {
          return "nfo_count"
        }

        if (
          contentMode
          === "files"
        ) {
          return "file_count"
        }

        return "media_count"
      },
      [
        contentMode,
      ],
    )


  const countLabel =
    contentMode === "nfo"
      ? "NFO"
      : contentMode === "files"
        ? "Files"
        : "Media"


  const ordering =
    descending
      ? `-${sortField}`
      : sortField


  const load =
    useCallback(
      async () => {
        setLoading(true)
        setError(null)

        try {
          const result =
            await getLibraryBrowser(
              libraryId,
              path,
              contentMode,
              ordering,
              search,
              page,
              pageSize,
            )

          setData(
            result
          )

        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : (
                "Unable to browse "
                + "this folder."
              )
          )

        } finally {
          setLoading(false)
        }
      },
      [
        libraryId,
        path,
        contentMode,
        ordering,
        search,
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


  useEffect(
    () => {
      setPage(1)
      setSearch("")
    },
    [
      path,
      contentMode,
    ],
  )


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
    field: LibraryBrowserSort,
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


  function openEntry(
    entry: LibraryBrowserEntry,
  ) {
    if (
      entry.entry_type
      === "folder"
    ) {
      onPathChange(
        entry.relative_path
      )

      return
    }

    if (
      entry.entry_type
      === "media"
      && entry.media_item
      && onOpenMedia
    ) {
      onOpenMedia(
        entry.media_item
      )

      return
    }

    if (
      entry.entry_type
      === "nfo"
      && onOpenNfo
    ) {
      onOpenNfo(
        entry.id
      )
    }
  }


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
          gap-1
          rounded-md
          border
          bg-muted/30
          px-3
          py-2
          text-sm
        "
      >
        {
          data?.breadcrumbs.map(
            (
              breadcrumb,
              index,
            ) => (
              <div
                key={
                  breadcrumb.path
                  || "root"
                }
                className="
                  flex
                  items-center
                "
              >
                {index > 0 && (
                  <span
                    className="
                      px-1
                      text-muted-foreground
                    "
                  >
                    /
                  </span>
                )}

                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="
                    h-7
                    px-2
                  "
                  onClick={
                    () =>
                      onPathChange(
                        breadcrumb.path
                      )
                  }
                >
                  {
                    index === 0
                      ? (
                        <Home
                          className="
                            mr-1
                            h-3.5
                            w-3.5
                          "
                        />
                      )
                      : null
                  }

                  {
                    breadcrumb.name
                  }
                </Button>
              </div>
            )
          )
        }
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
        placeholder="Search this folder..."
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
            min-w-[760px]
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
                <BrowserSortButton
                  label="Name"
                  field="name"
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
                Type
              </th>

              <th
                className="
                  p-3
                "
              >
                <BrowserSortButton
                  label={
                    countLabel
                  }
                  field={
                    countSortField
                  }
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

              {
                contentMode
                !== "nfo"
                && (
                  <th
                    className="
                      p-3
                    "
                  >
                    <BrowserSortButton
                      label="Duration"
                      field="duration_seconds"
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
                )
              }

              <th
                className="
                  p-3
                "
              >
                <BrowserSortButton
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
              loading
              && !data
              && (
                <tr>
                  <td
                    colSpan={
                      contentMode
                      === "nfo"
                        ? 4
                        : 5
                    }
                    className="
                      p-8
                      text-center
                      text-muted-foreground
                    "
                  >
                    Loading folder...
                  </td>
                </tr>
              )
            }

            {
              !loading
              && data
              && data.results.length
              === 0
              && (
                <tr>
                  <td
                    colSpan={
                      contentMode
                      === "nfo"
                        ? 4
                        : 5
                    }
                    className="
                      p-8
                      text-center
                      text-muted-foreground
                    "
                  >
                    This folder is empty.
                  </td>
                </tr>
              )
            }

            {
              data?.results.map(
                (
                  entry
                ) => (
                  <tr
                    key={
                      `${entry.entry_type}-${entry.relative_path}`
                    }
                    onClick={
                      () =>
                        openEntry(
                          entry
                        )
                    }
                    className={
                      (
                        entry.entry_type
                        === "folder"

                        || (
                          entry.entry_type
                          === "media"
                          && Boolean(
                            onOpenMedia
                          )
                        )

                        || (
                          entry.entry_type
                          === "nfo"
                          && Boolean(
                            onOpenNfo
                          )
                        )
                      )
                        ? `
                          cursor-pointer
                          border-b
                          hover:bg-muted/50
                        `
                        : "border-b"
                    }
                  >
                    <td
                      className="
                        p-3
                      "
                    >
                      <div
                        className="
                          flex
                          min-w-0
                          items-center
                          gap-2
                        "
                      >
                        {
                          entry.entry_type
                          === "folder"
                            ? (
                              <Folder
                                className="
                                  h-4
                                  w-4
                                  shrink-0
                                "
                              />
                            )
                            : entry.entry_type
                              === "media"
                              ? (
                                <FileVideo2
                                  className="
                                    h-4
                                    w-4
                                    shrink-0
                                  "
                                />
                              )
                              : entry.entry_type
                                === "artwork"
                                ? (
                                  <FileImage
                                    className="
                                      h-4
                                      w-4
                                      shrink-0
                                    "
                                  />
                                )
                                : (
                                  <FileText
                                    className="
                                      h-4
                                      w-4
                                      shrink-0
                                    "
                                  />
                                )
                        }

                        <div
                          className="
                            min-w-0
                          "
                        >
                          <div
                            className="
                              truncate
                              font-medium
                            "
                            title={
                              entry.title
                            }
                          >
                            {
                              entry.title
                            }
                          </div>

                          {
                            entry.entry_type
                            !== "folder"
                            && (
                              <div
                                className="
                                  truncate
                                  text-xs
                                  text-muted-foreground
                                "
                                title={
                                  entry.name
                                }
                              >
                                {
                                  entry.name
                                }
                              </div>
                            )
                          }
                        </div>
                      </div>
                    </td>

                    <td
                      className="
                        p-3
                        capitalize
                      "
                    >
                      {
                        entry.entry_type
                      }
                    </td>

                    <td
                      className="
                        p-3
                        tabular-nums
                      "
                    >
                      {
                        contentMode
                        === "nfo"
                          ? entry.nfo_count
                              .toLocaleString()
                          : contentMode
                            === "files"
                            ? entry.file_count
                                .toLocaleString()
                            : entry.media_count
                                .toLocaleString()
                      }

                      {
                        entry.entry_type
                        === "folder"
                        && contentMode
                        === "files"
                        && (
                          <div
                            className="
                              text-xs
                              text-muted-foreground
                            "
                          >
                            {
                              entry.media_count
                                .toLocaleString()
                            }
                            {" media · "}
                            {
                              entry.nfo_count
                                .toLocaleString()
                            }
                            {" NFO · "}
                            {
                              entry.artwork_count
                                .toLocaleString()
                            }
                            {" artwork"}
                          </div>
                        )
                      }
                    </td>

                    {
                      contentMode
                      !== "nfo"
                      && (
                        <td
                          className="
                            p-3
                            tabular-nums
                          "
                        >
                          {
                            entry.duration_seconds
                            ? formatDuration(
                              entry.duration_seconds
                            )
                            : "—"
                          }
                        </td>
                      )
                    }

                    <td
                      className="
                        p-3
                        tabular-nums
                      "
                    >
                      {
                        formatBytes(
                          entry.size_bytes
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

      {data && (
        <TablePagination
          page={
            data.page
          }
          pageSize={
            pageSize
          }
          totalPages={
            data.total_pages
          }
          count={
            data.count
          }
          onPageChange={
            setPage
          }
          onPageSizeChange={
            handlePageSizeChange
          }
        />
      )}
    </div>
  )
}
