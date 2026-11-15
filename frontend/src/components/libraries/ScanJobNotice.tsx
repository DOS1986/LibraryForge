import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"

import { cancelScanJob, getScanWorkerStatus } from "@/lib/api"

import type { ScanJob, ScanWorkerStatus } from "@/types"


const ACTIVE = ["queued", "discovering", "running"]

const WORKER_COMMAND = "uv run python manage.py run_scan_worker"


function WorkerHelp() {
  return (
    <span>
      Start it from the <code>backend</code> folder with <code>{WORKER_COMMAND}</code>, or start the whole app with{" "}
      <code>scripts/dev.ps1</code>, which runs the web server and the worker together.
    </span>
  )
}


/** Explains a queued, stalled, or cancelling scan and offers Cancel. */
export function ScanJobNotice({
  job,
  onChanged,
}: {
  job: ScanJob
  onChanged: (job: ScanJob) => void
}) {
  const [cancelling, setCancelling] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const active = ACTIVE.includes(job.status)

  if (!active) {
    return null
  }

  async function cancel() {
    setCancelling(true)
    setError(null)
    try {
      onChanged(await cancelScanJob(job.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to cancel the scan.")
    } finally {
      setCancelling(false)
    }
  }

  return (
    <div className="space-y-2 text-sm">
      {job.waiting_for_worker && (
        <div className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3" role="status">
          <span className="font-medium">Waiting for the scan worker.</span> No scan worker is running, so this scan
          won&apos;t start yet. <WorkerHelp />
        </div>
      )}

      {job.stalled && (
        <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3" role="alert">
          <span className="font-medium">This scan stopped.</span> The worker that was running it is no longer
          running. Start a new scan to replace it; this one will be marked as interrupted.
        </div>
      )}

      {job.cancel_requested && !job.stalled && (
        <p className="text-muted-foreground" role="status">
          Cancelling... the scan stops at its next checkpoint.
        </p>
      )}

      {!job.cancel_requested && (
        <Button variant="outline" size="sm" disabled={cancelling} onClick={() => void cancel()}>
          {cancelling ? "Cancelling..." : "Cancel scan"}
        </Button>
      )}

      {error && <p className="text-destructive" role="alert">{error}</p>}
    </div>
  )
}


/** Shows whether a scan worker is running. */
export function ScanWorkerBanner() {
  const [status, setStatus] = useState<ScanWorkerStatus | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const data = await getScanWorkerStatus()
        if (!cancelled) {
          setStatus(data)
        }
      } catch {
        // Status is informational; leave the last known value.
      }
    }

    void load()
    const timer = window.setInterval(() => void load(), 10_000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  if (!status) {
    return null
  }

  if (!status.alive) {
    return (
      <div className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 text-sm" role="status">
        <span className="font-medium">No scan worker is running.</span>{" "}
        {status.queued_jobs > 0
          ? `${status.queued_jobs} queued scan${status.queued_jobs === 1 ? " is" : "s are"} waiting. `
          : "New scans will wait in the queue. "}
        <WorkerHelp />
      </div>
    )
  }

  const worker = status.workers[0]

  return (
    <div className="text-sm text-muted-foreground" role="status">
      Scan worker running{worker ? ` on ${worker.hostname}` : ""}
      {worker?.current_library ? `, scanning ${worker.current_library}` : ", idle"}.
    </div>
  )
}
