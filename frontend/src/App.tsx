import {
  useEffect,
  useState,
} from "react"

import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from "react-router-dom"

import {
  AppShell,
} from "@/components/app/AppShell"

import {
  RestartingSplash,
  StartupSplash,
} from "@/components/app/RestartSplash"

import {
  LoginScreen,
} from "@/components/auth/LoginScreen"

import {
  getMe,
} from "@/lib/api"

import {
  UserSettingsProvider,
} from "@/lib/user-settings"

import {
  DashboardPage,
} from "@/pages/DashboardPage"

import {
  JobsPage,
} from "@/pages/JobsPage"

import {
  SettingsPage,
} from "@/pages/SettingsPage"

import {
  IntegrationsPage,
} from "@/pages/IntegrationsPage"

import {
  SystemStatusPage,
} from "@/pages/SystemStatusPage"

import {
  LibraryFilesPage,
} from "@/pages/libraries/LibraryFilesPage"

import {
  LibraryLayout,
} from "@/pages/libraries/LibraryLayout"

import {
  LibraryMediaPage,
} from "@/pages/libraries/LibraryMediaPage"

import {
  LibraryNfoPage,
} from "@/pages/libraries/LibraryNfoPage"

import {
  LibraryNeedsAttentionPage,
} from "@/pages/libraries/LibraryNeedsAttentionPage"

import {
  LibraryOverviewPage,
} from "@/pages/libraries/LibraryOverviewPage"

import {
  LibraryProjectionsPage,
} from "@/pages/libraries/LibraryProjectionsPage"

import {
  LibrarySettingsPage,
} from "@/pages/libraries/LibrarySettingsPage"

import {
  LibrarySourcesPage,
} from "@/pages/libraries/LibrarySourcesPage"

import type {
  User,
} from "@/types"


function App() {
  const [user, setUser] =
    useState<User | null>(null)

  const [loading, setLoading] =
    useState(true)

  const [bootReady, setBootReady] =
    useState(
      () =>
        window.sessionStorage.getItem(
          "libraryforge.show-startup-splash",
        ) !== "1",
    )

  const [restartRuntime, setRestartRuntime] =
    useState<string | null>(null)


  useEffect(
    () => {
      if (!bootReady) {
        return
      }

      setLoading(true)

      getMe()
        .then((result) => setUser(result.user))
        .catch(() => setUser(null))
        .finally(() => setLoading(false))
    },
    [bootReady],
  )


  if (restartRuntime) {
    return (
      <RestartingSplash
        previousRuntimeStartedAt={restartRuntime}
      />
    )
  }


  if (!bootReady) {
    return (
      <StartupSplash
        onComplete={() => {
          window.sessionStorage.removeItem(
            "libraryforge.show-startup-splash",
          )
          setBootReady(true)
        }}
      />
    )
  }


  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        Loading LibraryForge...
      </main>
    )
  }


  if (!user) {
    return (
      <LoginScreen
        onLogin={setUser}
      />
    )
  }


  return (
    <BrowserRouter>
      <UserSettingsProvider>
        <Routes>
          <Route
            element={(
              <AppShell
                user={user}
                onLogout={() => setUser(null)}
                onRestartStarted={(result) => {
                  setRestartRuntime(
                    result.runtime_started_at,
                  )
                }}
              />
            )}
          >
            <Route
              index
              element={<DashboardPage />}
            />

            <Route
              path="settings"
              element={<SettingsPage />}
            />

            <Route
              path="settings/integrations"
              element={<IntegrationsPage />}
            />

            <Route
              path="system"
              element={<SystemStatusPage />}
            />

            <Route
              path="libraries/:libraryId"
              element={<LibraryLayout />}
            >
              <Route
                index
                element={(
                  <Navigate
                    to="overview"
                    replace
                  />
                )}
              />

              <Route
                path="overview"
                element={<LibraryOverviewPage />}
              />

              <Route
                path="media"
                element={<LibraryMediaPage />}
              />

              <Route
                path="files"
                element={<LibraryFilesPage />}
              />

              <Route
                path="nfo"
                element={<LibraryNfoPage />}
              />

              <Route
                path="sources"
                element={<LibrarySourcesPage />}
              />

              <Route
                path="attention"
                element={<LibraryNeedsAttentionPage />}
              />

              <Route
                path="projections"
                element={<LibraryProjectionsPage />}
              />

              <Route
                path="settings"
                element={<LibrarySettingsPage />}
              />
            </Route>

            <Route
              path="jobs"
              element={<JobsPage />}
            />

            <Route
              path="*"
              element={(
                <Navigate
                  to="/"
                  replace
                />
              )}
            />
          </Route>
        </Routes>
      </UserSettingsProvider>
    </BrowserRouter>
  )
}


export default App
