import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import {
  ScanPanel,
} from "@/components/libraries/ScanPanel"

import {
  NeedsAttentionSummary,
} from "@/components/attention/NeedsAttentionSummary"

import {
  formatDateTime,
} from "@/lib/format"

import {
  useLibraryOutlet,
} from "@/lib/route-context"


export function LibraryOverviewPage() {
  const {
    library,
    refreshLibraries,
  } = useLibraryOutlet()


  return (
    <div
      className="
        space-y-6
      "
    >
      <Card>
        <CardHeader>
          <CardTitle>
            {library.name}
          </CardTitle>

          <CardDescription>
            {library.path}
          </CardDescription>
        </CardHeader>

        <CardContent
          className="
            grid
            gap-4
            md:grid-cols-4
          "
        >
          <div>
            <div
              className="
                text-sm
                text-muted-foreground
              "
            >
              Management Mode
            </div>

            <div
              className="
                font-medium
              "
            >
              {
                library
                  .management_mode_label
              }
            </div>
          </div>

          <div>
            <div
              className="
                text-sm
                text-muted-foreground
              "
            >
              Content Type
            </div>

            <div
              className="
                font-medium
              "
            >
              {
                library
                  .content_type_label
              }
            </div>
          </div>

          <div>
            <div
              className="
                text-sm
                text-muted-foreground
              "
            >
              Media Files
            </div>

            <div
              className="
                font-medium
              "
            >
              {
                library
                  .media_count
                  .toLocaleString()
              }
            </div>
          </div>

          <div>
            <div
              className="
                text-sm
                text-muted-foreground
              "
            >
              Last Scan
            </div>

            <div
              className="
                font-medium
              "
            >
              {
                formatDateTime(
                  library
                    .last_scanned_at
                )
              }
            </div>
          </div>
        </CardContent>
      </Card>

      <ScanPanel
        library={
          library
        }
        onComplete={
          refreshLibraries
        }
      />

      <NeedsAttentionSummary
        library={
          library
        }
      />
    </div>
  )
}
