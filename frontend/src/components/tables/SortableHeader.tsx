import {
  ArrowDown,
  ArrowUp,
  ChevronsUpDown,
} from "lucide-react"


export function SortableHeader({
  label,
  field,
  ordering,
  onChange,
  className = "",
}: {
  label: string
  field: string
  ordering: string
  onChange: (ordering: string) => void
  className?: string
}) {
  const descending =
    ordering === `-${field}`

  const ascending =
    ordering === field

  function toggle() {
    if (ascending) {
      onChange(`-${field}`)
      return
    }

    if (descending) {
      onChange(field)
      return
    }

    onChange(field)
  }

  return (
    <th className={`p-3 ${className}`}>
      <button
        type="button"
        onClick={toggle}
        className="inline-flex items-center gap-1 font-medium hover:underline"
      >
        {label}

        {ascending ? (
          <ArrowUp className="h-3.5 w-3.5" />
        ) : descending ? (
          <ArrowDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </button>
    </th>
  )
}
