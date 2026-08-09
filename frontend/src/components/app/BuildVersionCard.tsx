import {
  useEffect,
  useState,
} from "react"

import {
  AlertTriangle,
  CheckCircle2,
} from "lucide-react"

import {
  Badge,
} from "@/components/ui/badge"

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import {
  getSystemVersion,
} from "@/lib/api"

import {
  formatBuildIdentity,
  getFrontendBuildInfo,
  type FrontendBuildInfo,
} from "@/lib/version"

import type {
  SystemVersionInfo,
} from "@/types"


function knownSha(
  value:
    | string
    | null
    | undefined,
) {
  return Boolean(
    value
    && value !== "unknown"
  )
}


export function BuildVersionCard() {
  const [
    frontend,
    setFrontend,
  ] = useState<
    FrontendBuildInfo | null
  >(null)

  const [
    backend,
    setBackend,
  ] = useState<
    SystemVersionInfo | null
  >(null)

  const [
    frontendUnavailable,
    setFrontendUnavailable,
  ] = useState(false)

  const [
    backendUnavailable,
    setBackendUnavailable,
  ] = useState(false)


  useEffect(
    () => {
      let cancelled = false

      void getFrontendBuildInfo()
        .then(
          (
            result
          ) => {
            if (cancelled) {
              return
            }

            setFrontend(
              result
            )

            setFrontendUnavailable(
              false
            )
          }
        )
        .catch(
          () => {
            if (cancelled) {
              return
            }

            setFrontendUnavailable(
              true
            )
          }
        )

      void getSystemVersion()
        .then(
          (
            result
          ) => {
            if (cancelled) {
              return
            }

            setBackend(
              result
            )

            setBackendUnavailable(
              false
            )
          }
        )
        .catch(
          () => {
            if (cancelled) {
              return
            }

            setBackendUnavailable(
              true
            )
          }
        )

      return () => {
        cancelled = true
      }
    },
    [],
  )


  const versionMismatch = (
    frontend !== null
    && backend !== null
    && frontend.version
    !== backend.version
  )

  const commitMismatch = (
    frontend !== null
    && backend !== null
    && knownSha(
      frontend.git_sha
    )
    && knownSha(
      backend.git_sha
    )
    && frontend.git_sha
    !== backend.git_sha
  )

  const packageMismatch = (
    backend !== null
    && !backend
      .backend_version_consistent
  )

  const mismatch = (
    versionMismatch
    || commitMismatch
    || packageMismatch
  )


  return (
    <Card>
      <CardHeader
        className="
          pb-3
        "
      >
        <div
          className="
            flex
            items-center
            justify-between
            gap-3
          "
        >
          <CardTitle
            className="
              text-sm
            "
          >
            Build
          </CardTitle>

          {
            frontend
            && backend
            && (
              mismatch
                ? (
                  <Badge
                    variant="destructive"
                  >
                    Mismatch
                  </Badge>
                )
                : (
                  <Badge
                    variant="secondary"
                  >
                    <CheckCircle2
                      className="
                        mr-1
                        h-3
                        w-3
                      "
                    />

                    Synced
                  </Badge>
                )
            )
          }
        </div>
      </CardHeader>

      <CardContent
        className="
          space-y-3
          text-xs
        "
      >
        {
          frontend
          && (
            <div>
              <div
                className="
                  text-muted-foreground
                "
              >
                Frontend
              </div>

              <div
                className="
                  mt-1
                  font-mono
                "
              >
                {
                  formatBuildIdentity(
                    frontend.version,
                    frontend.git_short_sha,
                    frontend.git_dirty,
                  )
                }
              </div>
            </div>
          )
        }

        {
          backend
          && (
            <div>
              <div
                className="
                  text-muted-foreground
                "
              >
                Backend
              </div>

              <div
                className="
                  mt-1
                  font-mono
                "
              >
                {
                  formatBuildIdentity(
                    backend.version,
                    backend.git_short_sha,
                    backend.git_dirty,
                  )
                }
              </div>
            </div>
          )
        }

        {
          backend
          && (
            <div
              className="
                flex
                flex-wrap
                gap-x-3
                gap-y-1
                text-muted-foreground
              "
            >
              <span>
                {
                  backend.environment
                }
              </span>

              <span>
                Python {
                  backend.python_version
                }
              </span>

              <span>
                Django {
                  backend.django_version
                }
              </span>
            </div>
          )
        }

        {
          mismatch
          && (
            <div
              className="
                flex
                gap-2
                rounded-md
                border
                border-destructive/40
                bg-destructive/5
                p-2
                text-destructive
              "
            >
              <AlertTriangle
                className="
                  mt-0.5
                  h-3.5
                  w-3.5
                  shrink-0
                "
              />

              <span>
                Frontend/backend build identity
                does not match. Synchronize or
                rebuild before debugging
                application behavior.
              </span>
            </div>
          )
        }

        {
          (
            frontendUnavailable
            || backendUnavailable
          )
          && (
            <div
              className="
                text-muted-foreground
              "
            >
              {
                frontendUnavailable
                  ? (
                    "Frontend build metadata is unavailable. "
                  )
                  : ""
              }

              {
                backendUnavailable
                  ? (
                    "Backend build metadata is unavailable."
                  )
                  : ""
              }
            </div>
          )
        }
      </CardContent>
    </Card>
  )
}
