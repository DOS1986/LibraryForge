import {
  useEffect,
  useMemo,
  useState,
} from "react"

import {
  Hammer,
} from "lucide-react"

import type {
  SystemHealth,
} from "@/types"


const restartMessages = [
  "Reheating the forge...",
  "Sharpening the metadata...",
  "Asking ffmpeg nicely...",
  "Putting the posters back on the wall...",
  "Arguing with filenames...",
  "Waking PostgreSQL...",
  "Checking behind the couch for missing NFOs...",
  "Making sure 1917 is still a movie title...",
]

const startupMessages = [
  "Polishing the metadata hammer...",
  "Reorganizing the bits...",
  "Calibrating suspicious filenames...",
  "Definitely not judging Final_FINAL_v2.mkv...",
  "LibraryForge is almost ready...",
]


function SplashFrame({
  message,
  subtitle,
}: {
  message: string
  subtitle: string
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 p-6">
      <div className="w-full max-w-xl text-center">
        <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl border bg-background shadow-sm">
          <Hammer className="h-10 w-10" />
        </div>

        <div className="text-3xl font-bold tracking-tight">
          LibraryForge
        </div>

        <div className="mt-2 text-sm text-muted-foreground">
          {subtitle}
        </div>

        <div className="mt-8 rounded-lg border bg-background p-6 text-lg font-medium shadow-sm">
          {message}
        </div>

        <div className="mx-auto mt-6 h-2 max-w-sm overflow-hidden rounded-full bg-muted">
          <div className="h-full w-2/3 animate-pulse rounded-full bg-foreground/70" />
        </div>
      </div>
    </main>
  )
}


export function RestartingSplash({
  previousRuntimeStartedAt,
}: {
  previousRuntimeStartedAt: string
}) {
  const [messageIndex, setMessageIndex] =
    useState(0)

  useEffect(
    () => {
      const messageTimer = window.setInterval(
        () => {
          setMessageIndex(
            (value) =>
              (value + 1) % restartMessages.length,
          )
        },
        1100,
      )

      let stopped = false

      async function poll() {
        while (!stopped) {
          try {
            const response = await fetch(
              "/api/system/health/",
              {
                cache: "no-store",
              },
            )

            if (response.ok) {
              const health =
                await response.json() as SystemHealth

              if (
                health.runtime_started_at
                !== previousRuntimeStartedAt
              ) {
                window.sessionStorage.setItem(
                  "libraryforge.show-startup-splash",
                  "1",
                )

                window.location.reload()
                return
              }
            }
          } catch {
            // Expected while Django/Vite are restarting.
          }

          await new Promise<void>((resolve) => {
            window.setTimeout(resolve, 500)
          })
        }
      }

      void poll()

      return () => {
        stopped = true
        window.clearInterval(messageTimer)
      }
    },
    [previousRuntimeStartedAt],
  )

  return (
    <SplashFrame
      message={restartMessages[messageIndex]}
      subtitle="Restarting the application"
    />
  )
}


export function StartupSplash({
  onComplete,
}: {
  onComplete: () => void
}) {
  const messages = useMemo(
    () => startupMessages,
    [],
  )

  const [messageIndex, setMessageIndex] =
    useState(0)

  useEffect(
    () => {
      const messageTimer = window.setInterval(
        () => {
          setMessageIndex(
            (value) =>
              Math.min(
                value + 1,
                messages.length - 1,
              ),
          )
        },
        450,
      )

      const completeTimer = window.setTimeout(
        onComplete,
        2400,
      )

      return () => {
        window.clearInterval(messageTimer)
        window.clearTimeout(completeTimer)
      }
    },
    [messages.length, onComplete],
  )

  return (
    <SplashFrame
      message={messages[messageIndex]}
      subtitle="The forge is back online"
    />
  )
}
