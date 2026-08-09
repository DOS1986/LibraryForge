import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react"

import {
  Button,
} from "@/components/ui/button"

import type {
  PageSize,
} from "@/types"


const pageSizes:
  PageSize[] = [
    10,
    20,
    50,
    100,
  ]


interface TablePaginationProps {
  page: number
  pageSize: PageSize
  totalPages: number
  count: number

  onPageChange:
    (
      page: number
    ) => void

  onPageSizeChange:
    (
      pageSize: PageSize
    ) => void
}


export function TablePagination({
  page,
  pageSize,
  totalPages,
  count,
  onPageChange,
  onPageSizeChange,
}: TablePaginationProps) {
  const safeTotalPages =
    Math.max(
      1,
      totalPages,
    )

  const start =
    count === 0
      ? 0
      : (
        (
          page - 1
        )
        * pageSize
        + 1
      )

  const end =
    count === 0
      ? 0
      : Math.min(
        page * pageSize,
        count,
      )

  const hasPrevious =
    page > 1

  const hasNext =
    page < safeTotalPages


  return (
    <div
      className="
        flex
        flex-col
        gap-3
        border-t
        pt-4
        sm:flex-row
        sm:items-center
        sm:justify-between
      "
    >
      <div
        className="
          flex
          flex-wrap
          items-center
          gap-3
          text-sm
        "
      >
        <div
          className="
            flex
            items-center
            gap-2
          "
        >
          <span
            className="
              text-muted-foreground
            "
          >
            Rows per page
          </span>

          <select
            value={
              pageSize
            }
            onChange={
              (
                event
              ) =>
                onPageSizeChange(
                  Number(
                    event
                      .target
                      .value
                  ) as PageSize
                )
            }
            className="
              h-8
              rounded-md
              border
              bg-background
              px-2
              text-sm
            "
          >
            {
              pageSizes.map(
                (
                  size
                ) => (
                  <option
                    key={
                      size
                    }
                    value={
                      size
                    }
                  >
                    {size}
                  </option>
                )
              )
            }
          </select>
        </div>

        <span
          className="
            text-muted-foreground
          "
        >
          {
            start.toLocaleString()
          }
          {"–"}
          {
            end.toLocaleString()
          }
          {" of "}
          {
            count.toLocaleString()
          }
        </span>
      </div>

      <div
        className="
          flex
          flex-wrap
          items-center
          gap-2
        "
      >
        <span
          className="
            mr-2
            text-sm
            text-muted-foreground
          "
        >
          Page
          {" "}
          {page}
          {" of "}
          {
            safeTotalPages
          }
        </span>

        <Button
          type="button"
          variant="outline"
          size="icon"
          title="First page"
          disabled={
            !hasPrevious
          }
          onClick={
            () =>
              onPageChange(
                1
              )
          }
        >
          <ChevronsLeft
            className="
              h-4
              w-4
            "
          />
        </Button>

        <Button
          type="button"
          variant="outline"
          size="icon"
          title="Previous page"
          disabled={
            !hasPrevious
          }
          onClick={
            () =>
              onPageChange(
                Math.max(
                  1,
                  page - 1,
                )
              )
          }
        >
          <ChevronLeft
            className="
              h-4
              w-4
            "
          />
        </Button>

        <Button
          type="button"
          variant="outline"
          size="icon"
          title="Next page"
          disabled={
            !hasNext
          }
          onClick={
            () =>
              onPageChange(
                Math.min(
                  safeTotalPages,
                  page + 1,
                )
              )
          }
        >
          <ChevronRight
            className="
              h-4
              w-4
            "
          />
        </Button>

        <Button
          type="button"
          variant="outline"
          size="icon"
          title="Last page"
          disabled={
            !hasNext
          }
          onClick={
            () =>
              onPageChange(
                safeTotalPages
              )
          }
        >
          <ChevronsRight
            className="
              h-4
              w-4
            "
          />
        </Button>
      </div>
    </div>
  )
}
