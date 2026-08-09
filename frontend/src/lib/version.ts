export interface FrontendBuildInfo {
  name: string
  version: string
  git_sha: string | null
  git_short_sha: string | null
  git_branch: string | null
  git_dirty: boolean | null
  build_time: string
}


let cachedBuildInfo:
  FrontendBuildInfo | null = null


export async function getFrontendBuildInfo() {
  if (cachedBuildInfo) {
    return cachedBuildInfo
  }

  const response =
    await fetch(
      "/build-info.json",
      {
        cache:
          "no-store",
      },
    )

  if (!response.ok) {
    throw new Error(
      "Frontend build metadata is unavailable."
    )
  }

  cachedBuildInfo = (
    await response.json()
  ) as FrontendBuildInfo

  return cachedBuildInfo
}


export function formatBuildIdentity(
  version: string,
  shortSha?: string | null,
  dirty?: boolean | null,
) {
  const sha =
    shortSha
    || "unknown"

  return (
    `v${version} · ${sha}`
    + (
      dirty
        ? " · dirty"
        : ""
    )
  )
}
