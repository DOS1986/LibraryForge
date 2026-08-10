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
  TablePagination,
} from "@/components/tables/TablePagination"

import {
  getLibraryAssets,
} from "@/lib/api"

import {
  formatBytes,
} from "@/lib/format"

import {
  useLibraryOutlet,
} from "@/lib/route-context"

import type {
  LibraryAsset,
  PageSize,
} from "@/types"


type FilesView =
  | "folders"
  | "flat"


export function LibraryFilesPage() {
  const {
    library,
  } = useLibraryOutlet()

  const [
    searchParams,
    setSearchParams,
  ] = useSearchParams()

  const view: FilesView =
    searchParams.get(
      "view"
    ) === "flat"
      ? "flat"
      : "folders"

  const folderPath =
    searchParams.get(
      "folder"
    )
    ?? ""

  const [
    assets,
    setAssets,
  ] = useState<
    LibraryAsset[]
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


  const loadFlat =
    useCallback(
      async () => {
        const result =
          await getLibraryAssets(
            library.id,
            "relative_path",
            search,
            page,
            pageSize,
          )

        setAssets(
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
        page,
        pageSize,
      ],
    )


  useEffect(
    () => {
      if (view === "flat") {
        void loadFlat()
      }
    },
    [
      view,
      loadFlat,
    ],
  )


  function setView(
    nextView: FilesView,
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
      === "flat"
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


  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Files
        </CardTitle>

        <CardDescription>
          Navigate the physical folder tree or inspect every indexed media, NFO, and artwork asset in one flat list.
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
                (value as FilesView)
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
              value="flat"
            >
              Flat List
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
              contentMode="files"
              onPathChange={
                setFolderPath
              }
            />
          </TabsContent>

          <TabsContent
            value="flat"
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
              placeholder="Search all indexed files..."
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
                      Path
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
                      Size
                    </th>

                    <th
                      className="
                        p-3
                      "
                    >
                      Metadata
                    </th>

                    <th
                      className="
                        p-3
                      "
                    >
                      Present
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {
                    assets.map(
                      (
                        asset
                      ) => (
                        <tr
                          key={
                            `${asset.asset_type}-${asset.id}`
                          }
                          className="
                            border-b
                          "
                        >
                          <td
                            className="
                              p-3
                            "
                          >
                            {
                              asset.relative_path
                            }
                          </td>

                          <td
                            className="
                              p-3
                              capitalize
                            "
                          >
                            {
                              asset.asset_type
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
                                asset.size_bytes
                              )
                            }
                          </td>

                          <td
                            className="
                              p-3
                            "
                          >
                            {
                              asset.metadata_status
                            }
                          </td>

                          <td
                            className="
                              p-3
                            "
                          >
                            {
                              asset.is_present
                                ? "✓"
                                : "Missing"
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
  )
}
