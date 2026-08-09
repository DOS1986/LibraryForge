import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
} from "lucide-react"

import type {
  MediaSort,
} from "@/types"


interface SortHeaderProps {
  label: string
  field: MediaSort
  currentField: MediaSort
  descending: boolean

  onSort:
    (
      field: MediaSort
    ) => void
}


export function SortHeader({
  label,
  field,
  currentField,
  descending,
  onSort,
}: SortHeaderProps) {
  const active =
    currentField === field

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
