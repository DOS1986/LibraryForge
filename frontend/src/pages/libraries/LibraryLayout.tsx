import { Navigate, Outlet, useLocation, useParams } from "react-router-dom"

import { PageHeader } from "@/components/app/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"

import { libraryIcon, librarySection } from "@/lib/navigation"
import { useAppOutlet } from "@/lib/route-context"

import type { LibraryOutletContext } from "@/lib/route-context"


export function LibraryLayout() {
  const { libraryId } = useParams()
  const { pathname } = useLocation()
  const { libraries, librariesLoading, refreshLibraries } = useAppOutlet()

  if (!libraryId) {
    return <Navigate to="/" replace />
  }

  if (librariesLoading && !libraries.length) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-14 w-80 rounded-xl" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    )
  }

  const library = libraries.find(item => item.id === libraryId)

  if (!library) {
    return (
      <div className="rounded-xl border border-dashed bg-card/50 px-6 py-14 text-center text-muted-foreground">
        This library wasn&apos;t found. It may have been removed.
      </div>
    )
  }

  const section = librarySection(pathname.split("/")[3] ?? "overview")
  const Icon = libraryIcon(library)
  const context: LibraryOutletContext = { library, refreshLibraries }

  return (
    <>
      <PageHeader
        icon={<Icon className="size-5" />}
        eyebrow={library.name}
        title={section && section.path !== "overview" ? section.label : library.name}
        description={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <span className="truncate font-mono text-xs" title={library.path}>{library.path}</span>
            <Badge variant="secondary">{library.content_type_label}</Badge>
            <Badge variant={library.management_mode === "read_only" ? "outline" : "default"}>
              {library.management_mode_label}
            </Badge>
          </span>
        }
      />
      <Outlet context={context} />
    </>
  )
}
