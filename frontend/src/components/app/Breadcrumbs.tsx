import { Fragment } from "react"

import { ChevronRight } from "lucide-react"
import { Link, useLocation } from "react-router-dom"

import { MAIN_NAV, SETUP_NAV, librarySection } from "@/lib/navigation"

import type { Library } from "@/types"


interface Crumb {
  label: string
  to?: string
}


function crumbsFor(pathname: string, libraries: Library[]): Crumb[] {
  const library = pathname.match(/^\/libraries\/([^/]+)(?:\/([^/]+))?/)
  if (library) {
    const item = libraries.find(value => value.id === library[1])
    const section = librarySection(library[2] ?? "overview")
    const crumbs: Crumb[] = [{ label: "Libraries" }, { label: item?.name ?? "Library", to: `/libraries/${library[1]}/overview` }]
    if (section && section.path !== "overview") {
      crumbs.push({ label: section.label })
    }
    return crumbs
  }
  if (pathname === "/settings/integrations") {
    return [{ label: "Setup" }, { label: "Integrations" }]
  }
  const page = [...MAIN_NAV, ...SETUP_NAV].find(item => item.path === pathname)
  if (page && SETUP_NAV.includes(page)) {
    return [{ label: "Setup" }, { label: page.label }]
  }
  return [{ label: page?.label ?? "Dashboard" }]
}


export function Breadcrumbs({ libraries }: { libraries: Library[] }) {
  const { pathname } = useLocation()
  const crumbs = crumbsFor(pathname, libraries)

  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1
          return (
            <Fragment key={`${crumb.label}-${index}`}>
              {index > 0 && <ChevronRight aria-hidden className="size-3.5 shrink-0 text-muted-foreground/60" />}
              <li className={last ? "min-w-0 truncate font-medium text-foreground" : "hidden shrink-0 text-muted-foreground sm:block"}>
                {crumb.to && !last ? (
                  <Link to={crumb.to} className="rounded hover:text-foreground">{crumb.label}</Link>
                ) : (
                  <span aria-current={last ? "page" : undefined}>{crumb.label}</span>
                )}
              </li>
            </Fragment>
          )
        })}
      </ol>
    </nav>
  )
}
