import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
} from "react"

import {
  Badge,
} from "@/components/ui/badge"

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
  Input,
} from "@/components/ui/input"

import {
  Label,
} from "@/components/ui/label"

import {
  createOutputProfile,
  createProjection,
  getOutputProfiles,
  getProjections,
  previewProjection,
  runProjection,
} from "@/lib/api"

import {
  useLibraryOutlet,
} from "@/lib/route-context"

import type {
  OutputProfile,
  Projection,
  ProjectionPreview,
  ProjectionRunResult,
} from "@/types"


type OutputTarget =
  | "jellyfin"
  | "emby"
  | "kodi"
  | "generic"

type LinkMode =
  | "symlink"
  | "hardlink"
  | "copy"


export function LibraryProjectionsPage() {
  const {
    library,
  } = useLibraryOutlet()

  const [
    profiles,
    setProfiles,
  ] = useState<
    OutputProfile[]
  >([])

  const [
    projections,
    setProjections,
  ] = useState<
    Projection[]
  >([])

  const [
    profileName,
    setProfileName,
  ] = useState(
    "Jellyfin"
  )

  const [
    profileTarget,
    setProfileTarget,
  ] = useState<
    OutputTarget
  >(
    "jellyfin"
  )

  const [
    projectionName,
    setProjectionName,
  ] = useState("")

  const [
    destinationPath,
    setDestinationPath,
  ] = useState("")

  const [
    linkMode,
    setLinkMode,
  ] = useState<
    LinkMode
  >(
    "symlink"
  )

  const [
    namingTemplate,
    setNamingTemplate,
  ] = useState(
    "{channel}/{date} - {title} [{youtube_id}]"
  )

  const [
    outputProfileId,
    setOutputProfileId,
  ] = useState("")

  const [
    preview,
    setPreview,
  ] = useState<
    ProjectionPreview
    | null
  >(null)

  const [
    runResult,
    setRunResult,
  ] = useState<
    ProjectionRunResult
    | null
  >(null)

  const [
    error,
    setError,
  ] = useState<
    string | null
  >(null)


  const load =
    useCallback(
      async () => {
        const [
          profileResult,
          projectionResult,
        ] = await Promise.all([
          getOutputProfiles(),

          getProjections(
            library.id
          ),
        ])

        setProfiles(
          profileResult
        )

        setProjections(
          projectionResult
        )

        setOutputProfileId(
          (
            current
          ) =>
            current
            || profileResult[
              0
            ]?.id
            || ""
        )
      },
      [
        library.id,
      ],
    )


  useEffect(
    () => {
      void load()
    },
    [
      load,
    ],
  )


  async function addProfile(
    event: FormEvent,
  ) {
    event.preventDefault()

    setError(null)

    try {
      await createOutputProfile({
        name:
          profileName,

        target:
          profileTarget,

        nfo_root_element:
          "movie",
      })

      await load()

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to create output profile."
      )
    }
  }


  async function addProjection(
    event: FormEvent,
  ) {
    event.preventDefault()

    if (!outputProfileId) {
      return
    }

    setError(null)

    try {
      await createProjection({
        library:
          library.id,

        output_profile:
          outputProfileId,

        name:
          projectionName,

        destination_path:
          destinationPath,

        link_mode:
          linkMode,

        naming_template:
          namingTemplate,

        generate_nfo:
          true,
      })

      setProjectionName("")
      setDestinationPath("")

      await load()

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to create projection."
      )
    }
  }


  return (
    <div
      className="
        space-y-6
      "
    >
      {error && (
        <div
          className="
            rounded-md
            border
            border-destructive/50
            bg-destructive/5
            p-4
            text-sm
            text-destructive
          "
        >
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>
            Output Profiles
          </CardTitle>

          <CardDescription>
            Define the target media player format for generated NFO files and projections.
          </CardDescription>
        </CardHeader>

        <CardContent
          className="
            space-y-4
          "
        >
          <div
            className="
              flex
              flex-wrap
              gap-2
            "
          >
            {
              profiles.map(
                (
                  profile
                ) => (
                  <Badge
                    key={
                      profile.id
                    }
                    variant="secondary"
                  >
                    {
                      profile.name
                    }
                    {" — "}
                    {
                      profile.target_label
                    }
                  </Badge>
                )
              )
            }
          </div>

          <form
            onSubmit={
              addProfile
            }
            className="
              grid
              gap-3
              md:grid-cols-[1fr_180px_auto]
            "
          >
            <Input
              value={
                profileName
              }
              onChange={
                (
                  event
                ) =>
                  setProfileName(
                    event
                      .target
                      .value
                  )
              }
              placeholder="Profile name"
              required
            />

            <select
              value={
                profileTarget
              }
              onChange={
                (
                  event
                ) =>
                  setProfileTarget(
                    (
                      event
                        .target
                        .value
                    ) as OutputTarget
                  )
              }
              className="
                h-9
                rounded-md
                border
                bg-background
                px-3
                text-sm
              "
            >
              <option
                value="jellyfin"
              >
                Jellyfin
              </option>

              <option
                value="emby"
              >
                Emby
              </option>

              <option
                value="kodi"
              >
                Kodi
              </option>

              <option
                value="generic"
              >
                Generic
              </option>
            </select>

            <Button
              type="submit"
            >
              Add Profile
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            Create Projection
          </CardTitle>

          <CardDescription>
            Build a separate media-player-facing library using symlinks, hardlinks, or copies.
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form
            onSubmit={
              addProjection
            }
            className="
              space-y-4
            "
          >
            <div
              className="
                grid
                gap-4
                md:grid-cols-2
              "
            >
              <div
                className="
                  space-y-2
                "
              >
                <Label>
                  Name
                </Label>

                <Input
                  value={
                    projectionName
                  }
                  onChange={
                    (
                      event
                    ) =>
                      setProjectionName(
                        event
                          .target
                          .value
                      )
                  }
                  placeholder="TubeArchivist → Jellyfin"
                  required
                />
              </div>

              <div
                className="
                  space-y-2
                "
              >
                <Label>
                  Output Profile
                </Label>

                <select
                  value={
                    outputProfileId
                  }
                  onChange={
                    (
                      event
                    ) =>
                      setOutputProfileId(
                        event
                          .target
                          .value
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
                  required
                >
                  <option
                    value=""
                  >
                    Select profile
                  </option>

                  {
                    profiles.map(
                      (
                        profile
                      ) => (
                        <option
                          key={
                            profile.id
                          }
                          value={
                            profile.id
                          }
                        >
                          {
                            profile.name
                          }
                        </option>
                      )
                    )
                  }
                </select>
              </div>

              <div
                className="
                  space-y-2
                "
              >
                <Label>
                  Destination
                </Label>

                <Input
                  value={
                    destinationPath
                  }
                  onChange={
                    (
                      event
                    ) =>
                      setDestinationPath(
                        event
                          .target
                          .value
                      )
                  }
                  placeholder={
                    String.raw`\\server\media\YouTube-Jellyfin`
                  }
                  required
                />
              </div>

              <div
                className="
                  space-y-2
                "
              >
                <Label>
                  File Strategy
                </Label>

                <select
                  value={
                    linkMode
                  }
                  onChange={
                    (
                      event
                    ) =>
                      setLinkMode(
                        (
                          event
                            .target
                            .value
                        ) as LinkMode
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
                  <option
                    value="symlink"
                  >
                    Symbolic Link
                  </option>

                  <option
                    value="hardlink"
                  >
                    Hardlink
                  </option>

                  <option
                    value="copy"
                  >
                    Copy
                  </option>
                </select>
              </div>
            </div>

            <div
              className="
                space-y-2
              "
            >
              <Label>
                Naming Template
              </Label>

              <Input
                value={
                  namingTemplate
                }
                onChange={
                  (
                    event
                  ) =>
                    setNamingTemplate(
                      event
                        .target
                        .value
                    )
                }
              />
            </div>

            <Button
              type="submit"
            >
              Create Projection
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            Projections
          </CardTitle>
        </CardHeader>

        <CardContent
          className="
            space-y-3
          "
        >
          {
            projections.map(
              (
                projection
              ) => (
                <div
                  key={
                    projection.id
                  }
                  className="
                    rounded-md
                    border
                    p-4
                  "
                >
                  <div
                    className="
                      flex
                      flex-wrap
                      items-start
                      justify-between
                      gap-3
                    "
                  >
                    <div>
                      <div
                        className="
                          font-medium
                        "
                      >
                        {
                          projection.name
                        }
                      </div>

                      <div
                        className="
                          text-sm
                          text-muted-foreground
                        "
                      >
                        {
                          projection
                            .output_profile_name
                        }
                        {" · "}
                        {
                          projection
                            .link_mode_label
                        }
                      </div>

                      <div
                        className="
                          mt-1
                          break-all
                          text-xs
                          text-muted-foreground
                        "
                      >
                        {
                          projection
                            .destination_path
                        }
                      </div>
                    </div>

                    <div
                      className="
                        flex
                        gap-2
                      "
                    >
                      <Button
                        type="button"
                        variant="outline"
                        onClick={
                          async () => {
                            setPreview(
                              await previewProjection(
                                projection.id
                              )
                            )
                          }
                        }
                      >
                        Preview
                      </Button>

                      <Button
                        type="button"
                        onClick={
                          async () => {
                            setRunResult(
                              await runProjection(
                                projection.id
                              )
                            )
                          }
                        }
                      >
                        Run
                      </Button>
                    </div>
                  </div>
                </div>
              )
            )
          }

          {preview && (
            <div
              className="
                rounded-md
                border
                p-4
              "
            >
              <div
                className="
                  font-medium
                "
              >
                Preview
              </div>

              <div
                className="
                  mt-1
                  text-sm
                  text-muted-foreground
                "
              >
                Showing
                {" "}
                {
                  preview.preview_count
                }
                {" of "}
                {
                  preview.total
                }
              </div>

              <div
                className="
                  mt-3
                  max-h-80
                  space-y-2
                  overflow-y-auto
                "
              >
                {
                  preview.items.map(
                    (
                      item
                    ) => (
                      <div
                        key={
                          item.media_file_id
                        }
                        className="
                          rounded
                          bg-muted
                          p-3
                          text-xs
                        "
                      >
                        <div
                          className="
                            font-medium
                          "
                        >
                          {
                            item.title
                          }
                        </div>

                        <div
                          className="
                            break-all
                          "
                        >
                          {
                            item.destination_media_path
                          }
                        </div>

                        {
                          item.destination_nfo_path
                          && (
                            <div
                              className="
                                break-all
                              "
                            >
                              {
                                item.destination_nfo_path
                              }
                            </div>
                          )
                        }
                      </div>
                    )
                  )
                }
              </div>
            </div>
          )}

          {runResult && (
            <div
              className="
                rounded-md
                border
                p-4
                text-sm
              "
            >
              Created:
              {" "}
              {
                runResult.created
              }
              {" · Existing: "}
              {
                runResult.already_exists
              }
              {" · Errors: "}
              {
                runResult.error_count
              }
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
