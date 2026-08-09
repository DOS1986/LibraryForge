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
  Label,
} from "@/components/ui/label"

import {
  updateLibrarySettings,
} from "@/lib/api"

import {
  useLibraryOutlet,
} from "@/lib/route-context"

import type {
  LibraryContentType,
} from "@/types"


export function LibrarySettingsPage() {
  const {
    library,
    refreshLibraries,
  } = useLibraryOutlet()

  const [
    contentType,
    setContentType,
  ] = useState<
    LibraryContentType
  >(
    library.content_type
  )

  const [
    saving,
    setSaving,
  ] = useState(false)

  const [
    message,
    setMessage,
  ] = useState<
    string | null
  >(null)


  useEffect(
    () => {
      setContentType(
        library.content_type
      )
    },
    [
      library.content_type,
    ],
  )


  async function save() {
    setSaving(true)
    setMessage(null)

    try {
      await updateLibrarySettings(
        library.id,
        {
          content_type:
            contentType,
        },
      )

      await refreshLibraries()

      setMessage(
        "Library settings saved. "
        + "Run a scan to rebuild semantic "
        + "catalog matches for this type."
      )

    } catch (err) {
      setMessage(
        err instanceof Error
          ? err.message
          : "Unable to save library settings."
      )

    } finally {
      setSaving(false)
    }
  }


  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Library Settings
        </CardTitle>

        <CardDescription>
          Configure how LibraryForge interprets this source.
        </CardDescription>
      </CardHeader>

      <CardContent
        className="
          space-y-6
        "
      >
        <div>
          <div
            className="
              text-sm
              text-muted-foreground
            "
          >
            Name
          </div>

          <div>
            {library.name}
          </div>
        </div>

        <div>
          <div
            className="
              text-sm
              text-muted-foreground
            "
          >
            Path
          </div>

          <div
            className="
              break-all
            "
          >
            {library.path}
          </div>
        </div>

        <div>
          <div
            className="
              text-sm
              text-muted-foreground
            "
          >
            Management Mode
          </div>

          <div>
            {
              library
                .management_mode_label
            }
          </div>
        </div>

        <div
          className="
            max-w-md
            space-y-2
          "
        >
          <Label>
            Content Type
          </Label>

          <select
            value={
              contentType
            }
            onChange={
              (
                event
              ) =>
                setContentType(
                  (
                    event
                      .target
                      .value
                  ) as LibraryContentType
                )
            }
            className="
              h-9
              w-full
              rounded-md
              border
              bg-background
              px-3
              text-sm
            "
          >
            <option value="auto">
              Automatic
            </option>

            <option value="movies">
              Movies
            </option>

            <option value="tv">
              TV Shows
            </option>

            <option value="online_video">
              Online Video
            </option>

            <option value="mixed">
              Mixed Media
            </option>

            <option value="generic">
              Generic Video
            </option>
          </select>

          <p
            className="
              text-xs
              text-muted-foreground
            "
          >
            Movies and TV use semantic
            catalog matching during scans.
          </p>
        </div>

        <Button
          type="button"
          onClick={
            save
          }
          disabled={
            saving
            || contentType
            === library.content_type
          }
        >
          {
            saving
              ? "Saving..."
              : "Save Settings"
          }
        </Button>

        {message && (
          <p
            className="
              text-sm
              text-muted-foreground
            "
          >
            {message}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
