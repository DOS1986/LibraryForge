import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import {
  useAppOutlet,
} from "@/lib/route-context"


export function DashboardPage() {
  const {
    libraries,
    librariesLoading,
  } = useAppOutlet()

  if (librariesLoading) {
    return (
      <Card>
        <CardContent
          className="
            py-12
            text-center
            text-muted-foreground
          "
        >
          Loading dashboard...
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Dashboard
        </CardTitle>

        <CardDescription>
          LibraryForge library overview.
        </CardDescription>
      </CardHeader>

      <CardContent
        className="
          grid
          gap-4
          md:grid-cols-3
        "
      >
        <div
          className="
            rounded-md
            border
            p-4
          "
        >
          <div
            className="
              text-2xl
              font-bold
            "
          >
            {
              libraries.length
            }
          </div>

          <div
            className="
              text-sm
              text-muted-foreground
            "
          >
            Libraries
          </div>
        </div>

        <div
          className="
            rounded-md
            border
            p-4
          "
        >
          <div
            className="
              text-2xl
              font-bold
            "
          >
            {
              libraries.reduce(
                (
                  total,
                  library,
                ) =>
                  total
                  + library.media_count,
                0,
              )
              .toLocaleString()
            }
          </div>

          <div
            className="
              text-sm
              text-muted-foreground
            "
          >
            Media Files
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
