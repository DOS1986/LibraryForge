import { Link } from "react-router-dom"

import { ProjectionPanel } from "@/components/projections/ProjectionPanel"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

import { useLibraryOutlet } from "@/lib/route-context"


export function LibraryProjectionsPage() {
  const { library } = useLibraryOutlet()
  const projectable = ["movies", "tv", "online_video", "mixed"].includes(library.content_type)
  // Movie and TV libraries usually only need NFOs written beside the media.
  const nfoInstead = ["movies", "tv", "mixed"].includes(library.content_type) && library.management_mode !== "read_only"

  return (
    <div className="space-y-6">
      {nfoInstead && (
        <div className="rounded-lg border bg-muted/40 p-3 text-sm" role="note">
          <p>
            <span className="font-medium">You may not need a folder here.</span> If your media server already recognizes
            this library&apos;s titles, NFOs and artwork written into the library itself are all it needs, with no second
            library to add. Set them up on the{" "}
            <Link className="font-medium underline underline-offset-4" to={`/libraries/${library.id}/nfo`}>NFO</Link> page.
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            A folder here is for names the server gets wrong, or for another media server that needs its own artwork names.
          </p>
        </div>
      )}

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
