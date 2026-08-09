import {
  useEffect,
  useState,
} from "react"

import {
  Link,
} from "react-router-dom"

import {
  AlertTriangle,
} from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import {
  getSemanticMatchPage,
} from "@/lib/api"

import type {
  Library,
} from "@/types"


export function NeedsAttentionSummary({
  library,
}: {
  library: Library
}) {
  const [
    unresolved,
    setUnresolved,
  ] = useState(0)

  const [
    conflicts,
    setConflicts,
  ] = useState(0)


  useEffect(
    () => {
      if (
        library.content_type
        === "online_video"
        || library.content_type
        === "generic"
      ) {
        setUnresolved(0)
        setConflicts(0)
        return
      }

      void Promise.all([
        getSemanticMatchPage(
          library.id,
          {
            status:
              "unresolved",

            page:
              1,

            pageSize:
              10,
          },
        ),

        getSemanticMatchPage(
          library.id,
          {
            status:
              "conflict",

            page:
              1,

            pageSize:
              10,
          },
        ),
      ]).then(
        ([
          unresolvedResult,
          conflictResult,
        ]) => {
          setUnresolved(
            unresolvedResult.count
          )

          setConflicts(
            conflictResult.count
          )
        }
      )
    },
    [
      library.id,
      library.content_type,
      library.last_scanned_at,
    ],
  )


  const total =
    unresolved
    + conflicts

  if (
    total === 0
  ) {
    return null
  }


  return (
    <Card
      className="
        border-amber-500/40
      "
    >
      <CardHeader>
        <div
          className="
            flex
            items-start
            justify-between
            gap-4
          "
        >
          <div>
            <CardTitle
              className="
                flex
                items-center
                gap-2
              "
            >
              <AlertTriangle
                className="
                  h-5
                  w-5
                "
              />

              Needs Attention
            </CardTitle>

            <CardDescription>
              Some semantic identities require
              review before LibraryForge should
              trust them.
            </CardDescription>
          </div>

          <Link
            to={
              `/libraries/${library.id}/attention`
            }
            className="
              inline-flex
              h-9
              items-center
              justify-center
              rounded-md
              border
              bg-background
              px-4
              text-sm
              font-medium
              shadow-sm
              transition-colors
              hover:bg-accent
              hover:text-accent-foreground
            "
          >
            Review
          </Link>
        </div>
      </CardHeader>

      <CardContent
        className="
          flex
          flex-wrap
          gap-6
          text-sm
        "
      >
        <div>
          <div
            className="
              text-2xl
              font-bold
            "
          >
            {unresolved}
          </div>

          <div
            className="
              text-muted-foreground
            "
          >
            Unresolved
          </div>
        </div>

        <div>
          <div
            className="
              text-2xl
              font-bold
            "
          >
            {conflicts}
          </div>

          <div
            className="
              text-muted-foreground
            "
          >
            Conflicts
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
