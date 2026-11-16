import { ChevronRight } from "lucide-react"
import { Link } from "react-router-dom"

import { StatTile } from "@/components/app/PageHeader"
import { NeedsAttentionSummary } from "@/components/attention/NeedsAttentionSummary"
import { ScanPanel } from "@/components/libraries/ScanPanel"

import { formatDateTime } from "@/lib/format"
import { LIBRARY_SECTIONS } from "@/lib/navigation"
import { useLibraryOutlet } from "@/lib/route-context"


export function LibraryOverviewPage() {
  const { library, refreshLibraries } = useLibraryOutlet()
  const sections = LIBRARY_SECTIONS.filter(section => section.path !== "overview")

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile label="Items catalogued" value={library.media_count.toLocaleString()} tone="brand" />
        <StatTile
          label="Last scan"
          value={library.last_scanned_at ? new Date(library.last_scanned_at).toLocaleDateString() : "Never"}
          tone={library.last_scanned_at ? "default" : "warning"}
          hint={library.last_scanned_at ? formatDateTime(library.last_scanned_at) : "Scan the library to catalog its files."}
        />
        <StatTile label="Content type" value={library.content_type_label} hint={library.management_mode_label} />
      </div>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-6">
          <ScanPanel library={library} onComplete={refreshLibraries} />
          <NeedsAttentionSummary library={library} />
        </div>

        <nav aria-label="Library pages" className="rounded-xl border bg-card p-2 shadow-xs">
          <div className="px-3 pt-2 pb-1 text-xs font-medium text-muted-foreground">Library pages</div>
          <ul>
            {sections.map(section => (
              <li key={section.path}>
                <Link
                  to={`/libraries/${library.id}/${section.path}`}
                  className="group flex items-center gap-3 rounded-lg px-3 py-2.5 outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground group-hover:text-foreground">
                    <section.icon className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium">{section.label}</span>
                    <span className="block truncate text-xs text-muted-foreground">{section.description}</span>
                  </span>
                  <ChevronRight className="size-4 text-muted-foreground/60" />
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </div>
  )
}
