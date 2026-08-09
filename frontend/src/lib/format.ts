import type {
  ManagementMode,
} from "@/types"


export function formatBytes(
  bytes: number,
) {
  if (bytes <= 0) {
    return "0 B"
  }

  const units = [
    "B",
    "KB",
    "MB",
    "GB",
    "TB",
    "PB",
  ]

  const index =
    Math.min(
      Math.floor(
        Math.log(bytes)
        / Math.log(1024)
      ),
      units.length - 1,
    )

  return (
    `${
      (
        bytes
        / Math.pow(
          1024,
          index,
        )
      ).toFixed(1)
    } ${units[index]}`
  )
}


export function formatDuration(
  seconds:
    | number
    | null,
) {
  if (seconds === null) {
    return "—"
  }

  const total =
    Math.max(
      0,
      Math.round(seconds),
    )

  const hours =
    Math.floor(
      total / 3600
    )

  const minutes =
    Math.floor(
      (
        total % 3600
      )
      / 60
    )

  const secs =
    total % 60

  if (hours > 0) {
    return [
      hours,

      minutes
        .toString()
        .padStart(
          2,
          "0",
        ),

      secs
        .toString()
        .padStart(
          2,
          "0",
        ),
    ].join(":")
  }

  return [
    minutes,

    secs
      .toString()
      .padStart(
        2,
        "0",
      ),
  ].join(":")
}


export function formatDateTime(
  value:
    | string
    | null,
) {
  if (!value) {
    return "—"
  }

  return (
    new Date(
      value
    ).toLocaleString()
  )
}


export function managementModeLabel(
  mode:
    | ManagementMode
    | null,
) {
  switch (mode) {
    case "full_control":
      return "Full Control"

    case "sidecar_only":
      return "Sidecar Only"

    case "read_only":
      return "Read Only"

    default:
      return "—"
  }
}
