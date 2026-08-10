import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"

import {
  Activity,
  ChevronDown,
  LogOut,
  RotateCcw,
  Settings,
} from "lucide-react"

import {
  useNavigate,
} from "react-router-dom"

import {
  Button,
} from "@/components/ui/button"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

import {
  requestSystemRestart,
} from "@/lib/api"

import {
  useUserSettings,
} from "@/lib/user-settings"

import type {
  RestartRequestResult,
  User,
} from "@/types"


function initialsFor(
  label: string,
  email: string,
) {
  const words = label
    .trim()
    .split(/\s+/)
    .filter(Boolean)

  if (words.length >= 2) {
    return (
      `${words[0][0]}${words[1][0]}`
      .toUpperCase()
    )
  }

  if (words.length === 1) {
    return words[0]
      .slice(0, 2)
      .toUpperCase()
  }

  return email
    .split("@")[0]
    .slice(0, 2)
    .toUpperCase()
}


interface AccountMenuProps {
  user: User
  onLogout: () => Promise<void>
  onRestartStarted: (
    result: RestartRequestResult,
  ) => void
}


export function AccountMenu({
  user,
  onLogout,
  onRestartStarted,
}: AccountMenuProps) {
  const [open, setOpen] =
    useState(false)

  const [restartOpen, setRestartOpen] =
    useState(false)

  const [restarting, setRestarting] =
    useState(false)

  const [restartError, setRestartError] =
    useState<string | null>(null)

  const containerRef =
    useRef<HTMLDivElement>(null)

  const navigate = useNavigate()

  const {
    settings,
  } = useUserSettings()


  const displayName = (
    settings?.display_name.trim()
    || user.displayName?.trim()
    || `${user.firstName ?? ""} ${user.lastName ?? ""}`.trim()
    || user.email
  )

  const initials = useMemo(
    () => initialsFor(
      displayName,
      user.email,
    ),
    [displayName, user.email],
  )

  const canRestart = (
    user.isStaff
    || user.isSuperuser
  )


  useEffect(
    () => {
      function handlePointerDown(
        event: MouseEvent,
      ) {
        if (
          containerRef.current
          && !containerRef.current.contains(
            event.target as Node,
          )
        ) {
          setOpen(false)
        }
      }

      document.addEventListener(
        "mousedown",
        handlePointerDown,
      )

      return () => {
        document.removeEventListener(
          "mousedown",
          handlePointerDown,
        )
      }
    },
    [],
  )


  function goTo(path: string) {
    setOpen(false)
    navigate(path)
  }


  async function startRestart() {
    setRestarting(true)
    setRestartError(null)

    try {
      const result =
        await requestSystemRestart()

      setRestartOpen(false)
      setOpen(false)
      onRestartStarted(result)
    } catch (err) {
      setRestartError(
        err instanceof Error
          ? err.message
          : "Unable to request a restart.",
      )
      setRestartOpen(true)
      setOpen(false)
    } finally {
      setRestarting(false)
    }
  }


  function requestRestart() {
    setRestartError(null)

    if (settings?.confirm_restart ?? true) {
      setRestartOpen(true)
      setOpen(false)
      return
    }

    void startRestart()
  }


  return (
    <>
      <div
        ref={containerRef}
        className="relative"
      >
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="flex items-center gap-2 rounded-full border bg-background p-1 pr-2 transition hover:bg-muted"
          aria-expanded={open}
          aria-haspopup="menu"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
            {initials}
          </span>

          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </button>

        {open && (
          <div
            role="menu"
            className="absolute right-0 z-50 mt-2 w-72 overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-lg"
          >
            <div className="px-4 py-3">
              <div className="truncate font-medium">
                {displayName}
              </div>
              <div className="truncate text-sm text-muted-foreground">
                {user.email}
              </div>
            </div>

            <div className="border-t p-1">
              <button
                type="button"
                role="menuitem"
                onClick={() => goTo("/settings")}
                className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm hover:bg-muted"
              >
                <Settings className="h-4 w-4" />
                Settings
              </button>

              <button
                type="button"
                role="menuitem"
                onClick={() => goTo("/system")}
                className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm hover:bg-muted"
              >
                <Activity className="h-4 w-4" />
                System Status
              </button>

              {canRestart && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={requestRestart}
                  disabled={restarting}
                  className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm hover:bg-muted disabled:opacity-50"
                >
                  <RotateCcw className="h-4 w-4" />
                  Restart LibraryForge
                </button>
              )}
            </div>

            <div className="border-t p-1">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false)
                  void onLogout()
                }}
                className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm hover:bg-muted"
              >
                <LogOut className="h-4 w-4" />
                Log Out
              </button>
            </div>
          </div>
        )}
      </div>

      <Dialog
        open={restartOpen}
        onOpenChange={setRestartOpen}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Restart LibraryForge?
            </DialogTitle>
            <DialogDescription>
              The backend and development frontend will be restarted by the configured supervisor. Your current session will be signed out and the login screen will return after startup.
            </DialogDescription>
          </DialogHeader>

          {restartError && (
            <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
              {restartError}
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setRestartOpen(false)}
              disabled={restarting}
            >
              Cancel
            </Button>

            <Button
              type="button"
              onClick={() => void startRestart()}
              disabled={restarting}
            >
              {restarting ? "Requesting..." : "Restart LibraryForge"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
