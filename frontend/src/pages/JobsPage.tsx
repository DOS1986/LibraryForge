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
  TablePagination,
} from "@/components/tables/TablePagination"

import {
  getScanJobs,
} from "@/lib/api"

import {
  formatDateTime,
} from "@/lib/format"

import type {
  PageSize,
  ScanJob,
} from "@/types"


export function JobsPage() {
  const [
    jobs,
    setJobs,
  ] = useState<
    ScanJob[]
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
      let cancelled = false

      void getScanJobs(
        undefined,
        page,
        pageSize,
      ).then(
        (
          result
        ) => {
          if (cancelled) {
            return
          }

          setJobs(
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

      return () => {
        cancelled = true
      }
    },
    [
      page,
      pageSize,
    ],
  )


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
          Jobs
        </CardTitle>

        <CardDescription>
          {
            count
              .toLocaleString()
          }
          {" "}
          scan jobs.
        </CardDescription>
      </CardHeader>

      <CardContent
        className="
          space-y-4
        "
      >
        <div
          className="
            space-y-3
          "
        >
          {
            jobs.map(
              (
                job
              ) => (
                <div
                  key={
                    job.id
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
                      items-center
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
                          job.library_name
                        }
                      </div>

                      <div
                        className="
                          text-xs
                          text-muted-foreground
                        "
                      >
                        {
                          formatDateTime(
                            job.created_at
                          )
                        }
                      </div>
                    </div>

                    <Badge
                      variant={
                        job.status
                        === "failed"
                          ? "destructive"
                          : "secondary"
                      }
                    >
                      {
                        job.status_label
                      }
                    </Badge>
                  </div>
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
