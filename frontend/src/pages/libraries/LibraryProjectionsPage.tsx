import { Link } from "react-router-dom"

import { ProjectionPanel } from "@/components/projections/ProjectionPanel"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

import { useLibraryOutlet } from "@/lib/route-context"


export function LibraryProjectionsPage() {
  const { library } = useLibraryOutlet()
  const projectable = ["movies", "tv", "online_video", "mixed"].includes(library.content_type)

  return (
    <div className="space-y-6">
      {projectable ? (
        <ProjectionPanel libraryId={library.id} libraryPath={library.path} contentType={library.content_type} />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Projections</CardTitle>
            <CardDescription>
              Projections are available for movie, TV, online video, and mixed libraries. Set this library&apos;s content
              type in its Settings to project it.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      <p className="text-sm text-muted-foreground">
        Every library&apos;s outputs, recent runs, allowed output folders, and media server profiles are on the{" "}
        <Link className="font-medium text-foreground underline underline-offset-4" to="/outputs">Outputs</Link> page.
      </p>
    </div>
  )
}
