import {
  useEffect,
  useState,
} from "react"

import {
  Button,
} from "@/components/ui/button"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import {
  Progress,
} from "@/components/ui/progress"

import {
  getScanJob,
  getScanJobs,
  startLibraryScan,
} from "@/lib/api"

import type {
  Library,
  ScanJob,
} from "@/types"


const activeScanStatuses = [
  "queued",
  "discovering",
  "running",
]


interface ScanPanelProps {
  library: Library

  onComplete:
    () => Promise<void>
}


export function ScanPanel({
  library,
  onComplete,
}: ScanPanelProps) {
  const [
    job,
    setJob,
  ] = useState<
    ScanJob | null
  >(null)

  const [
    loadingJob,
    setLoadingJob,
  ] = useState(true)

  const [
    error,
    setError,
  ] = useState<
    string | null
  >(null)

  const active =
    job !== null
    && activeScanStatuses.includes(
      job.status
    )


  useEffect(
    () => {
      let cancelled = false

      async function recoverScanJob() {
        setLoadingJob(true)
        setError(null)

        try {
          const result =
            await getScanJobs(
              library.id
            )

          if (cancelled) {
            return
          }

          const activeJob =
            result.results.find(
              (
                candidate
              ) =>
                activeScanStatuses.includes(
                  candidate.status
                )
            )

          setJob(
            activeJob
            ?? null
          )

        } catch (err) {
          if (!cancelled) {
            setError(
              err instanceof Error
                ? err.message
                : (
                  "Unable to check "
                  + "scan status."
                )
            )
          }

        } finally {
          if (!cancelled) {
            setLoadingJob(false)
          }
        }
      }

      void recoverScanJob()

      return () => {
        cancelled = true
      }
    },
    [
      library.id,
    ],
  )


  async function start() {
    setError(null)

    try {
      const scanJob =
        await startLibraryScan(
          library.id
        )

      setJob(
        scanJob
      )

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to start scan."
      )
    }
  }


  useEffect(
    () => {
      if (!job) {
        return
      }

      if (
        !activeScanStatuses.includes(
          job.status
        )
      ) {
        return
      }

      let cancelled = false

      const timer =
        window.setTimeout(
          async () => {
            try {
              const updated =
                await getScanJob(
                  job.id
                )

              if (cancelled) {
                return
              }

              setJob(
                updated
              )

              if (
                [
                  "completed",
                  "completed_with_errors",
                  "failed",
                ].includes(
                  updated.status
                )
              ) {
                await onComplete()
              }

            } catch (err) {
              if (!cancelled) {
                setError(
                  err instanceof Error
                    ? err.message
                    : (
                      "Unable to read "
                      + "scan progress."
                    )
                )
              }
            }
          },
          750,
        )

      return () => {
        cancelled = true

        window.clearTimeout(
          timer
        )
      }
    },
    [
      job,
      onComplete,
    ],
  )


  return (
    <Card>
      <CardHeader
        className="
          flex
          flex-row
          items-start
          justify-between
          gap-4
        "
      >
        <div>
          <CardTitle>
            Library Scan
          </CardTitle>

          <CardDescription>
            Discover media, inspect technical metadata, and index existing NFO files.
          </CardDescription>
        </div>

        <Button
          onClick={
            start
          }
          disabled={
            active
            || loadingJob
          }
        >
          {
            loadingJob
              ? "Checking..."
              : active
                ? "Scanning..."
                : "Scan Library"
          }
        </Button>
      </CardHeader>

      {
        loadingJob
        && !job
        && (
          <CardContent>
            <div
              className="
                text-sm
                text-muted-foreground
              "
            >
              Checking for an active scan...
            </div>
          </CardContent>
        )
      }

      {
        job
        && (
          <CardContent
            className="
              space-y-4
            "
          >
            <div
              className="
                flex
                justify-between
                gap-4
                text-sm
              "
            >
              <strong>
                {
                  job.status_label
                }
              </strong>

              <span
                className="
                  tabular-nums
                  text-muted-foreground
                "
              >
                {
                  job.processed_files
                    .toLocaleString()
                }
                {" / "}
                {
                  job.total_files
                    .toLocaleString()
                }
              </span>
            </div>

            {
              job.status
              === "queued"
              && (
                <>
                  <Progress
                    value={0}
                  />

                  <p
                    className="
                      text-sm
                      text-muted-foreground
                    "
                  >
                    Waiting for the scan worker...
                  </p>
                </>
              )
            }

            {
              job.status
              === "discovering"
              && (
                <>
                  <Progress
                    value={0}
                    className="
                      animate-pulse
                    "
                  />

                  <p
                    className="
                      text-sm
                      text-muted-foreground
                    "
                  >
                    Discovering library files...
                    {" "}
                    {
                      job.total_files
                        .toLocaleString()
                    }
                    {" "}
                    found so far
                  </p>
                </>
              )
            }

            {
              (
                job.status
                === "running"

                || job.status
                === "completed"

                || job.status
                === "completed_with_errors"

                || job.status
                === "failed"
              )
              && (
                <>
                  <Progress
                    value={
                      job.progress_percent
                    }
                  />

                  <div
                    className="
                      flex
                      justify-between
                      text-xs
                      text-muted-foreground
                    "
                  >
                    <span>
                      {
                        job.progress_percent
                      }
                      %
                    </span>

                    <span>
                      {
                        job.processed_files
                          .toLocaleString()
                      }
                      {" / "}
                      {
                        job.total_files
                          .toLocaleString()
                      }
                    </span>
                  </div>
                </>
              )
            }

            <div
              className="
                grid
                gap-3
                sm:grid-cols-3
              "
            >
              <div
                className="
                  rounded-md
                  border
                  p-3
                "
              >
                <div
                  className="
                    text-sm
                    font-medium
                  "
                >
                  Overall
                </div>

                <div
                  className="
                    mt-1
                    tabular-nums
                  "
                >
                  {
                    job.processed_files
                      .toLocaleString()
                  }
                  {" / "}
                  {
                    job.total_files
                      .toLocaleString()
                  }
                </div>
              </div>

              <div
                className="
                  rounded-md
                  border
                  p-3
                "
              >
                <div
                  className="
                    text-sm
                    font-medium
                  "
                >
                  Media
                </div>

                <div
                  className="
                    mt-1
                    tabular-nums
                  "
                >
                  {
                    job.processed_media_files
                      .toLocaleString()
                  }
                  {" / "}
                  {
                    job.total_media_files
                      .toLocaleString()
                  }
                </div>
              </div>

              <div
                className="
                  rounded-md
                  border
                  p-3
                "
              >
                <div
                  className="
                    text-sm
                    font-medium
                  "
                >
                  NFO
                </div>

                <div
                  className="
                    mt-1
                    tabular-nums
                  "
                >
                  {
                    job.processed_nfo_files
                      .toLocaleString()
                  }
                  {" / "}
                  {
                    job.total_nfo_files
                      .toLocaleString()
                  }
                </div>
              </div>
            </div>

            <div
              className="
                grid
                gap-3
                sm:grid-cols-5
              "
            >
              {
                [
                  [
                    "Created",
                    job.created_count,
                  ],

                  [
                    "Updated",
                    job.updated_count,
                  ],

                  [
                    "Unchanged",
                    job.skipped_count,
                  ],

                  [
                    "NFO",
                    (
                      job.nfo_created_count
                      + job.nfo_updated_count
                    ),
                  ],

                  [
                    "Errors",
                    job.error_count,
                  ],
                ].map(
                  ([
                    label,
                    value,
                  ]) => (
                    <div
                      key={
                        String(
                          label
                        )
                      }
                      className="
                        rounded-md
                        border
                        p-3
                      "
                    >
                      <div
                        className="
                          text-lg
                          font-semibold
                          tabular-nums
                        "
                      >
                        {
                          Number(
                            value
                          ).toLocaleString()
                        }
                      </div>

                      <div
                        className="
                          text-xs
                          text-muted-foreground
                        "
                      >
                        {label}
                      </div>
                    </div>
                  )
                )
              }
            </div>

            {
              job.current_path
              && (
                <p
                  className="
                    truncate
                    text-xs
                    text-muted-foreground
                  "
                  title={
                    job.current_path
                  }
                >
                  Current:
                  {" "}
                  {
                    job.current_path
                  }
                </p>
              )
            }

            {
              job.errors.length
              > 0
              && (
                <div
                  className="
                    rounded-md
                    border
                    p-3
                  "
                >
                  <div
                    className="
                      mb-2
                      text-sm
                      font-medium
                    "
                  >
                    Scan Errors
                  </div>

                  <div
                    className="
                      max-h-40
                      space-y-2
                      overflow-y-auto
                    "
                  >
                    {
                      job.errors.map(
                        (
                          scanError,
                          index,
                        ) => (
                          <div
                            key={
                              `${scanError.path}-${index}`
                            }
                            className="
                              text-xs
                            "
                          >
                            <div
                              className="
                                break-all
                                font-medium
                              "
                            >
                              {
                                scanError.path
                              }
                            </div>

                            <div
                              className="
                                text-destructive
                              "
                            >
                              {
                                scanError.error
                              }
                            </div>
                          </div>
                        )
                      )
                    }
                  </div>
                </div>
              )
            }
          </CardContent>
        )
      }

      {
        error
        && (
          <CardContent>
            <p
              className="
                text-sm
                text-destructive
              "
            >
              {error}
            </p>
          </CardContent>
        )
      }
    </Card>
  )
}
