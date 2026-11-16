import { useCallback, useEffect, useState } from "react"

import { Search } from "lucide-react"
import { Outlet, useNavigate } from "react-router-dom"

import { AccountMenu } from "@/components/app/AccountMenu"
import { AppSidebar } from "@/components/app/AppSidebar"
import { Breadcrumbs } from "@/components/app/Breadcrumbs"
import { CommandPalette } from "@/components/app/CommandPalette"
import { ThemeMenu } from "@/components/app/ThemeMenu"
import { CreateLibraryCard } from "@/components/libraries/CreateLibraryCard"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { Separator } from "@/components/ui/separator"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"

import { getLibraries, logout } from "@/lib/api"

import type { AppOutletContext } from "@/lib/route-context"
import type { Library, RestartRequestResult, User } from "@/types"


interface AppShellProps {
  user: User
  onLogout: () => void
  onRestartStarted: (result: RestartRequestResult) => void
}


// The sidebar component remembers open/collapsed in this cookie.
function sidebarStartsOpen() {
  return !document.cookie.split("; ").includes("sidebar_state=false")
}


const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)


export function AppShell({ user, onLogout, onRestartStarted }: AppShellProps) {
  const [libraries, setLibraries] = useState<Library[]>([])
  const [librariesLoading, setLibrariesLoading] = useState(true)
  const [searchOpen, setSearchOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const navigate = useNavigate()

  const refreshLibraries = useCallback(async () => {
    setLibrariesLoading(true)
    try {
      setLibraries(await getLibraries())
    } finally {
      setLibrariesLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshLibraries()
  }, [refreshLibraries])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        setSearchOpen(value => !value)
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])

  const openAdd = useCallback(() => setAddOpen(true), [])

  async function handleCreated(library: Library) {
    setAddOpen(false)
    await refreshLibraries()
    navigate(`/libraries/${library.id}/overview`)
  }

  async function handleSignOut() {
    await logout()
    onLogout()
  }

  const outletContext: AppOutletContext = { libraries, librariesLoading, refreshLibraries, openAddLibrary: openAdd }

  return (
    <SidebarProvider defaultOpen={sidebarStartsOpen()}>
      <AppSidebar libraries={libraries} loading={librariesLoading} onAddLibrary={openAdd} />

      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur supports-[backdrop-filter]:bg-background/70 md:px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-1 h-5" />
          <Breadcrumbs libraries={libraries} />

          <div className="ml-auto flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="w-9 justify-start gap-2 px-2.5 text-muted-foreground sm:w-56"
              onClick={() => setSearchOpen(true)}
              aria-label="Quick search"
            >
              <Search />
              <span className="hidden flex-1 text-left sm:inline">Search...</span>
              <kbd className="hidden rounded border bg-muted px-1.5 text-[0.6875rem] font-normal sm:inline">
                {isMac ? "⌘" : "Ctrl"} K
              </kbd>
            </Button>
            <ThemeMenu />
            <AccountMenu user={user} onLogout={handleSignOut} onRestartStarted={onRestartStarted} />
          </div>
        </header>

        <div className="mx-auto w-full max-w-[1600px] flex-1 space-y-6 px-4 py-6 md:px-8 md:py-8">
          <Outlet context={outletContext} />
        </div>
      </SidebarInset>

      <CommandPalette open={searchOpen} onOpenChange={setSearchOpen} libraries={libraries} onAddLibrary={openAdd} />

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto border-0 bg-transparent p-0 shadow-none ring-0 sm:max-w-2xl">
          <DialogTitle className="sr-only">Add a library</DialogTitle>
          <CreateLibraryCard onCreated={handleCreated} />
        </DialogContent>
      </Dialog>
    </SidebarProvider>
  )
}
