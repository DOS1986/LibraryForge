import type {
  SemanticMatchProvenance,
} from "@/types"


export async function getSemanticMatchProvenance(
  matchId: string,
) {
  const response = await fetch(
    `/api/semantic-matches/${matchId}/provenance/`,
    {
      credentials: "include",
    },
  )

  if (!response.ok) {
    let message = "Unable to load semantic provenance."

    try {
      const data = await response.json() as Record<string, unknown>
      if (typeof data.detail === "string") {
        message = data.detail
      }
    } catch {
      // Keep the generic message when the response is not JSON.
    }

    throw new Error(message)
  }

  return await response.json() as SemanticMatchProvenance
}
