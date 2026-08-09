import {
  useEffect,
  useState,
} from "react"

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
  TablePagination,
} from "@/components/tables/TablePagination"

import {
  getMetadataSources,
} from "@/lib/api"

import {
  useLibraryOutlet,
} from "@/lib/route-context"

import type {
  MetadataSource,
  PageSize,
} from "@/types"


type SourceFilter =
  | "all"
  | "tubearchivist"
  | "yt_dlp"


export function LibrarySourcesPage() {
  const {
    library,
  } = useLibraryOutlet()

  const [
    sourceType,
    setSourceType,
  ] = useState<
    SourceFilter
  >(
    "all"
  )

  const [
    sources,
    setSources,
  ] = useState<
    MetadataSource[]
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


  useEffect(
    () => {
      void getMetadataSources(
        library.id,

        sourceType
        === "all"
          ? undefined
          : sourceType,

        sourceType
        === "all"
          ? undefined
          : "detected",

        page,
        pageSize,
      ).then(
        (
          result
        ) => {
          setSources(
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
      library.id,
      sourceType,
      page,
      pageSize,
    ],
  )


  function handleSourceTypeChange(
    value: SourceFilter,
  ) {
    setSourceType(value)
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
          Metadata Sources
        </CardTitle>

        <CardDescription>
          {
            count
              .toLocaleString()
          }
          {" "}
          matching metadata source records.
        </CardDescription>
      </CardHeader>

      <CardContent
        className="
          space-y-4
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
            [
              [
                "all",
                "All",
              ],

              [
                "tubearchivist",
                "TubeArchivist",
              ],

              [
                "yt_dlp",
                "yt-dlp",
              ],
            ].map(
              ([
                value,
                label,
              ]) => (
                <Button
                  key={value}
                  type="button"
                  variant={
                    sourceType
                    === value
                      ? "default"
                      : "outline"
                  }
                  onClick={
                    () =>
                      handleSourceTypeChange(
                        (value as SourceFilter)
                      )
                  }
                >
                  {label}
                </Button>
              )
            )
          }
        </div>

        <div
          className="
            space-y-3
          "
        >
          {
            sources.length
            === 0
            && (
              <div
                className="
                  py-8
                  text-center
                  text-sm
                  text-muted-foreground
                "
              >
                No matching metadata sources found.
              </div>
            )
          }

          {
            sources.map(
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
                    p-4
                  "
                >
                  <div
                    className="
                      flex
                      items-start
                      justify-between
                      gap-4
                    "
                  >
                    <div>
                      <div
                        className="
                          font-medium
                        "
                      >
                        {
                          source.media_title
                        }
                      </div>

                      <div
                        className="
                          text-xs
                          text-muted-foreground
                        "
                      >
                        {
                          source.relative_path
                        }
                      </div>
                    </div>

                    <Badge
                      variant="secondary"
                    >
                      {
                        source
                          .source_type_label
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
                          max-h-72
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
      </CardContent>
    </Card>
  )
}
