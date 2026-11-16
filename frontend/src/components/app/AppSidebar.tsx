import { useEffect, useState } from "react"

import { ChevronRight, Plus } from "lucide-react"
import { Link, useLocation } from "react-router-dom"

import { LogoMark, Wordmark } from "@/components/brand/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar"

import { LIBRARY_SECTIONS, MAIN_NAV, SETUP_NAV, libraryIcon, type NavItem } from "@/lib/navigation"
import { cn } from "@/lib/utils"

import type { Library } from "@/types"


const EXPANDED_KEY = "libraryforge.sidebar.libraries"


function storedExpanded(): string[] {
  try {
    const value = JSON.parse(window.localStorage.getItem(EXPANDED_KEY) || "[]")
    return Array.isArray(value) ? value.filter(item => typeof item === "string") : []
  } catch {
    return []
  }
}


function isActive(pathname: string, path: string) {
  if (path === "/") {
    return pathname === "/"
  }
  if (path === "/settings") {
    return pathname === "/settings"
  }
  return pathname === path || pathname.startsWith(`${path}/`)
}


function NavGroup({ items, label, pathname }: { items: NavItem[]; label?: string; pathname: string }) {
  return (
    <SidebarGroup>
      {label && <SidebarGroupLabel>{label}</SidebarGroupLabel>}
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map(item => (
            <SidebarMenuItem key={item.path}>
              <SidebarMenuButton
                isActive={isActive(pathname, item.path)}
                tooltip={item.label}
                render={<Link to={item.path} />}
              >
                <item.icon />
                <span>{item.label}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}


export function AppSidebar({
  libraries,
  loading,
  onAddLibrary,
}: {
  libraries: Library[]
  loading: boolean
  onAddLibrary: () => void
}) {
  const { pathname } = useLocation()
  const { state, isMobile, setOpenMobile } = useSidebar()
  const [expanded, setExpanded] = useState<string[]>(storedExpanded)
  const currentLibrary = pathname.match(/^\/libraries\/([^/]+)/)?.[1]
  const collapsed = state === "collapsed" && !isMobile

  // Opening a library expands it and folds the others away, so the sidebar
  // stays short; any library can still be expanded by hand.
  useEffect(() => {
    if (currentLibrary) {
      setExpanded([currentLibrary])
    }
  }, [currentLibrary])

  useEffect(() => {
    try {
      window.localStorage.setItem(EXPANDED_KEY, JSON.stringify(expanded))
    } catch {
      // Not remembered this time.
    }
  }, [expanded])

  // Close the slide-out after navigating on a phone.
  useEffect(() => {
    if (isMobile) {
      setOpenMobile(false)
    }
  }, [pathname, isMobile, setOpenMobile])

  function toggle(id: string) {
    setExpanded(value => (value.includes(id) ? value.filter(item => item !== id) : [...value, id]))
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="h-14 justify-center border-b border-sidebar-border px-3">
        <Link to="/" className="flex items-center gap-2.5 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring" aria-label="LibraryForge home">
          <LogoMark className="size-7" />
          <Wordmark className="text-base group-data-[collapsible=icon]:hidden" />
        </Link>
      </SidebarHeader>

      <SidebarContent>
        <NavGroup items={MAIN_NAV} pathname={pathname} />

        <SidebarGroup>
          <SidebarGroupLabel>Libraries</SidebarGroupLabel>
          <SidebarGroupAction title="Add a library" onClick={onAddLibrary}>
            <Plus />
            <span className="sr-only">Add a library</span>
          </SidebarGroupAction>
          <SidebarGroupContent>
            <SidebarMenu>
              {loading && Array.from({ length: 3 }, (_, index) => (
                <SidebarMenuItem key={index}>
                  <SidebarMenuSkeleton showIcon />
                </SidebarMenuItem>
              ))}

              {!loading && !libraries.length && (
                <SidebarMenuItem>
                  <SidebarMenuButton onClick={onAddLibrary} tooltip="Add a library">
                    <Plus />
                    <span>Add your first library</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              )}

              {!loading && libraries.map(library => {
                const Icon = libraryIcon(library)
                const open = expanded.includes(library.id)
                const base = `/libraries/${library.id}`
                const inLibrary = currentLibrary === library.id

                return (
                  <SidebarMenuItem key={library.id}>
                    {collapsed ? (
                      <SidebarMenuButton
                        isActive={inLibrary}
                        tooltip={library.name}
                        render={<Link to={`${base}/overview`} />}
                      >
                        <Icon />
                        <span>{library.name}</span>
                      </SidebarMenuButton>
                    ) : (
                      <SidebarMenuButton
                        isActive={inLibrary && !open}
                        aria-expanded={open}
                        onClick={() => toggle(library.id)}
                        className={cn(inLibrary && "font-medium")}
                      >
                        <Icon />
                        <span className="truncate">{library.name}</span>
                        <ChevronRight className={cn("ml-auto transition-transform", open && "rotate-90")} />
                      </SidebarMenuButton>
                    )}

                    {open && !collapsed && (
                      <SidebarMenuSub>
                        {LIBRARY_SECTIONS.map(section => {
                          const path = `${base}/${section.path}`
                          return (
                            <SidebarMenuSubItem key={section.path}>
                              <SidebarMenuSubButton isActive={pathname === path} render={<Link to={path} />}>
                                <section.icon />
                                <span>{section.label}</span>
                              </SidebarMenuSubButton>
                            </SidebarMenuSubItem>
                          )
                        })}
                      </SidebarMenuSub>
                    )}
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <NavGroup items={SETUP_NAV} label="Setup" pathname={pathname} />
      </SidebarContent>

      <SidebarRail />
    </Sidebar>
  )
}
