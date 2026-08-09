import {
  useCallback,
  useEffect,
  useState,
} from "react"

import {
  NavLink,
  Outlet,
  useNavigate,
} from "react-router-dom"

import {
  Button,
} from "@/components/ui/button"

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import {
  Separator,
} from "@/components/ui/separator"

import {
  BuildVersionCard,
} from "@/components/app/BuildVersionCard"

import {
  CreateLibraryCard,
} from "@/components/libraries/CreateLibraryCard"

import {
  getLibraries,
  logout,
} from "@/lib/api"

import type {
  AppOutletContext,
} from "@/lib/route-context"

import type {
  Library,
  User,
} from "@/types"


const librarySections = [
  {
    path:
      "overview",

    label:
      "Overview",
  },
  {
    path:
      "media",

    label:
      "Media",
  },
  {
    path:
      "files",

    label:
      "Files",
  },
  {
    path:
      "nfo",

    label:
      "NFO",
  },
  {
    path:
      "sources",

    label:
      "Sources",
  },
  {
    path:
      "attention",

    label:
      "Needs Attention",
  },
  {
    path:
      "projections",

    label:
      "Projections",
  },
  {
    path:
      "settings",

    label:
      "Settings",
  },
] as const


interface AppShellProps {
  user: User

  onLogout:
    () => void
}


export function AppShell({
  user,
  onLogout,
}: AppShellProps) {
  const [
    libraries,
    setLibraries,
  ] = useState<
    Library[]
  >([])

  const [
    librariesLoading,
    setLibrariesLoading,
  ] = useState(true)

  const navigate =
    useNavigate()


  const refreshLibraries =
    useCallback(
      async () => {
        setLibrariesLoading(
          true
        )

        try {
          setLibraries(
            await getLibraries()
          )

        } finally {
          setLibrariesLoading(
            false
          )
        }
      },
      [],
    )


  useEffect(
    () => {
      void refreshLibraries()
    },
    [
      refreshLibraries,
    ],
  )


  async function handleCreated(
    library: Library,
  ) {
    await refreshLibraries()

    navigate(
      `/libraries/${library.id}/overview`
    )
  }


  async function handleSignOut() {
    await logout()

    onLogout()
  }


  const outletContext:
    AppOutletContext = {
      libraries,
      librariesLoading,
      refreshLibraries,
    }


  return (
    <main
      className="
        min-h-screen
        bg-muted/30
      "
    >
      <header
        className="
          border-b
          bg-background
        "
      >
        <div
          className="
            mx-auto
            flex
            max-w-[1800px]
            items-center
            justify-between
            px-6
            py-4
          "
        >
          <div>
            <div
              className="
                text-2xl
                font-bold
              "
            >
              LibraryForge
            </div>

            <div
              className="
                text-sm
                text-muted-foreground
              "
            >
              Your media. Your metadata. Your structure.
            </div>
          </div>

          <div
            className="
              flex
              items-center
              gap-4
            "
          >
            <span
              className="
                text-sm
                text-muted-foreground
              "
            >
              {user.email}
            </span>

            <Button
              variant="outline"
              onClick={
                handleSignOut
              }
            >
              Sign Out
            </Button>
          </div>
        </div>
      </header>

      <div
        className="
          mx-auto
          grid
          max-w-[1800px]
          gap-6
          p-6
          xl:grid-cols-[340px_1fr]
        "
      >
        <aside
          className="
            space-y-6
          "
        >
          <Card>
            <CardHeader>
              <CardTitle>
                Navigation
              </CardTitle>
            </CardHeader>

            <CardContent
              className="
                space-y-4
              "
            >
              <NavLink
                to="/"
                end
                className={
                  ({
                    isActive,
                  }) =>
                    (
                      "block rounded-md px-3 py-2 "
                      + (
                        isActive
                          ? "bg-primary text-primary-foreground"
                          : "hover:bg-muted"
                      )
                    )
                }
              >
                Dashboard
              </NavLink>

              {
                librariesLoading
                ? (
                  <div
                    className="
                      text-sm
                      text-muted-foreground
                    "
                  >
                    Loading libraries...
                  </div>
                )
                : (
                  <div
                    className="
                      space-y-3
                    "
                  >
                    {
                      libraries.map(
                        (
                          library
                        ) => (
                          <div
                            key={
                              library.id
                            }
                            className="
                              rounded-md
                              border
                              p-3
                            "
                          >
                            <div
                              className="
                                font-medium
                              "
                            >
                              {
                                library.name
                              }
                            </div>

                            <div
                              className="
                                mt-1
                                truncate
                                text-xs
                                text-muted-foreground
                              "
                            >
                              {
                                library.path
                              }
                            </div>

                            <div
                              className="
                                mt-3
                                grid
                                grid-cols-2
                                gap-1
                                text-xs
                              "
                            >
                              {
                                librarySections.map(
                                  (
                                    section
                                  ) => (
                                    <NavLink
                                      key={
                                        section.path
                                      }
                                      to={
                                        `/libraries/${library.id}/${section.path}`
                                      }
                                      className={
                                        ({
                                          isActive,
                                        }) =>
                                          (
                                            "rounded px-2 py-1 "
                                            + (
                                              isActive
                                                ? "bg-primary text-primary-foreground"
                                                : "hover:bg-muted"
                                            )
                                          )
                                      }
                                    >
                                      {
                                        section.label
                                      }
                                    </NavLink>
                                  )
                                )
                              }
                            </div>
                          </div>
                        )
                      )
                    }
                  </div>
                )
              }

              <Separator />

              <NavLink
                to="/jobs"
                className={
                  ({
                    isActive,
                  }) =>
                    (
                      "block rounded-md px-3 py-2 "
                      + (
                        isActive
                          ? "bg-primary text-primary-foreground"
                          : "hover:bg-muted"
                      )
                    )
                }
              >
                Jobs
              </NavLink>
            </CardContent>
          </Card>

          <CreateLibraryCard
            onCreated={
              handleCreated
            }
          />

          <BuildVersionCard />
        </aside>

        <section>
          <Outlet
            context={
              outletContext
            }
          />
        </section>
      </div>
    </main>
  )
}
