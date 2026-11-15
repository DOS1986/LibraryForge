import { ArrowRight, Clapperboard, Plus, ShieldCheck, TriangleAlert } from "lucide-react"
import { Link } from "react-router-dom"

import { BuildVersionCard } from "@/components/app/BuildVersionCard"
import { PageHeader, StatTile } from "@/components/app/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

import { libraryIcon } from "@/lib/navigation"
import { useAppOutlet } from "@/lib/route-context"
import { useUserSettings } from "@/lib/user-settings"

import type { Library } from "@/types"


function relativeTime(value: string | null) {
  if (!value) {
    return "Never scanned"
  }
  const seconds = (Date.now() - new Date(value).getTime()) / 1000
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"],
    [60, "minute"],
    [24, "hour"],
    [30, "day"],
    [12, "month"],
    [Number.POSITIVE_INFINITY, "year"],
  ]
  let amount = -seconds
  for (const [size, unit] of units) {
    if (Math.abs(amount) < size) {
      return `Scanned ${new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(Math.round(amount), unit)}`
    }
    amount /= size
  }
  return "Scanned"
}


function LibraryCard({ library }: { library: Library }) {
  const Icon = libraryIcon(library)
  const base = `/libraries/${library.id}`
  const quick = [
    { to: `${base}/media`, label: "Media", icon: Clapperboard },
    { to: `${base}/ratings`, label: "Ratings", icon: ShieldCheck },
    { to: `${base}/attention`, label: "Attention", icon: TriangleAlert },
  ]

  return (
    <article className="group flex min-w-0 flex-col rounded-xl border bg-card shadow-xs transition-shadow hover:shadow-md">
      <Link to={`${base}/overview`} className="flex flex-1 items-start gap-3 rounded-t-xl p-5 outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary dark:bg-primary/15">
          <Icon className="size-5" />
        </span>
        <span className="min-w-0 flex-1 space-y-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-base font-semibold">{library.name}</span>
            <ArrowRight className="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
          </span>
          <span className="block truncate font-mono text-xs text-muted-foreground" title={library.path}>{library.path}</span>
          <span className="flex flex-wrap gap-1.5 pt-1">
            <Badge variant="secondary">{library.content_type_label}</Badge>
            <Badge variant={library.management_mode === "read_only" ? "outline" : "default"}>{library.management_mode_label}</Badge>
          </span>
        </span>
      </Link>
      <div className="flex items-center justify-between gap-3 border-t px-5 py-3">
        <div className="text-sm">
          <span className="font-semibold tabular-nums">{library.media_count.toLocaleString()}</span>{" "}
          <span className="text-muted-foreground">items · {relativeTime(library.last_scanned_at)}</span>
        </div>
        <div className="flex gap-1">
          {quick.map(item => (
            <Button key={item.to} variant="ghost" size="icon-sm" aria-label={`${library.name} ${item.label}`} title={item.label} render={<Link to={item.to} />}>
              <item.icon />
            </Button>
          ))}
        </div>
      </div>
    </article>
  )
}


export function DashboardPage() {
  const { libraries, librariesLoading, openAddLibrary } = useAppOutlet()
  const { settings } = useUserSettings()

  const total = libraries.reduce((sum, library) => sum + library.media_count, 0)
  const neverScanned = libraries.filter(library => !library.last_scanned_at).length
  const lastScan = libraries
    .map(library => library.last_scanned_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1) ?? null

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Your libraries at a glance. Pick one to browse its media, ratings, and files."
        actions={
          <Button onClick={openAddLibrary}>
            <Plus />
            Add library
          </Button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Libraries" value={librariesLoading ? "–" : libraries.length} tone="brand" />
        <StatTile label="Items catalogued" value={librariesLoading ? "–" : total.toLocaleString()} />
        <StatTile label="Last scan" value={librariesLoading ? "–" : relativeTime(lastScan).replace(/^Scanned /, "")} />
        <StatTile
          label="Never scanned"
          value={librariesLoading ? "–" : neverScanned}
          tone={neverScanned ? "warning" : "success"}
          hint={neverScanned ? "Scan them from their Overview page." : "Every library has been scanned."}
        />
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Libraries</h2>
        {librariesLoading ? (
          <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
            {Array.from({ length: 3 }, (_, index) => <Skeleton key={index} className="h-40 rounded-xl" />)}
          </div>
        ) : libraries.length ? (
          <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
            {libraries.map(library => <LibraryCard key={library.id} library={library} />)}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed bg-card/50 px-6 py-14 text-center">
            <span className="flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary"><Plus className="size-6" /></span>
            <div className="space-y-1">
              <p className="font-semibold">No libraries yet</p>
              <p className="text-sm text-muted-foreground">Add a folder of movies, shows, or online video to get started.</p>
            </div>
            <Button onClick={openAddLibrary}>Add your first library</Button>
          </div>
        )}
      </section>

      {(settings?.show_build_information ?? true) && (
        <section className="max-w-xl">
          <BuildVersionCard />
        </section>
      )}
    </>
  )
}
