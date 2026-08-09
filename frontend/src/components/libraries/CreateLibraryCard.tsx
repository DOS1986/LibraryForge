import {
  useState,
  type FormEvent,
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
  Input,
} from "@/components/ui/input"

import {
  Label,
} from "@/components/ui/label"

import {
  Separator,
} from "@/components/ui/separator"

import {
  createLibrary,
  testLibraryPath,
} from "@/lib/api"

import {
  managementModeLabel,
} from "@/lib/format"

import type {
  CapabilityStatus,
  Library,
  LibraryContentType,
  ManagementMode,
  StorageTestResult,
} from "@/types"


const capabilityLabels: Record<
  keyof StorageTestResult[
    "capabilities"
  ],
  string
> = {
  path_exists:
    "Path exists",

  directory:
    "Directory",

  read_access:
    "Read access",

  media_access:
    "Media files accessible",

  write_access:
    "Write access",

  sidecar_creation:
    "Sidecar creation",

  rename:
    "Rename",

  hardlink:
    "Hardlink",

  symlink:
    "Symlink",
}


function CapabilityMark({
  status,
}: {
  status: CapabilityStatus
}) {
  if (status === "passed") {
    return (
      <span
        className="
          font-bold
          text-emerald-600
        "
      >
        ✓
      </span>
    )
  }

  if (status === "failed") {
    return (
      <span
        className="
          font-bold
          text-destructive
        "
      >
        ✕
      </span>
    )
  }

  return (
    <span
      className="
        text-muted-foreground
      "
    >
      —
    </span>
  )
}


interface CreateLibraryCardProps {
  onCreated:
    (
      library: Library
    ) => void
}


export function CreateLibraryCard({
  onCreated,
}: CreateLibraryCardProps) {
  const [
    name,
    setName,
  ] = useState("")

  const [
    path,
    setPath,
  ] = useState("")

  const [
    managementMode,
    setManagementMode,
  ] = useState<
    ManagementMode
  >(
    "read_only"
  )

  const [
    contentType,
    setContentType,
  ] = useState<
    LibraryContentType
  >(
    "auto"
  )

  const [
    storageTest,
    setStorageTest,
  ] = useState<
    StorageTestResult
    | null
  >(null)

  const [
    testing,
    setTesting,
  ] = useState(false)

  const [
    error,
    setError,
  ] = useState<
    string | null
  >(null)


  function handlePathChange(
    value: string,
  ) {
    setPath(value)
    setStorageTest(null)
  }


  async function handleTestStorage() {
    if (!path.trim()) {
      return
    }

    setTesting(true)
    setError(null)

    try {
      setStorageTest(
        await testLibraryPath(
          path
        )
      )

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Storage test failed."
      )

    } finally {
      setTesting(false)
    }
  }


  async function handleSubmit(
    event: FormEvent,
  ) {
    event.preventDefault()

    setError(null)

    try {
      const library =
        await createLibrary({
          name,
          path,

          management_mode:
            managementMode,

          content_type:
            contentType,
        })

      setName("")
      setPath("")

      setManagementMode(
        "read_only"
      )

      setContentType(
        "auto"
      )

      setStorageTest(null)

      onCreated(
        library
      )

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to create library."
      )
    }
  }


  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Create Library
        </CardTitle>

        <CardDescription>
          The path must be visible to the server running LibraryForge.
        </CardDescription>
      </CardHeader>

      <CardContent>
        <form
          onSubmit={
            handleSubmit
          }
          className="
            space-y-4
          "
        >
          <div
            className="
              space-y-2
            "
          >
            <Label>
              Library Name
            </Label>

            <Input
              value={name}
              onChange={
                (
                  event
                ) =>
                  setName(
                    event
                      .target
                      .value
                  )
              }
              placeholder="Movies"
              required
            />
          </div>

          <div
            className="
              space-y-2
            "
          >
            <Label>
              Path
            </Label>

            <Input
              value={path}
              onChange={
                (
                  event
                ) =>
                  handlePathChange(
                    event
                      .target
                      .value
                  )
              }
              placeholder={
                String.raw`\\server\media\Movies`
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
              <option
                value="auto"
              >
                Automatic
              </option>

              <option
                value="movies"
              >
                Movies
              </option>

              <option
                value="tv"
              >
                TV Shows
              </option>

              <option
                value="online_video"
              >
                Online Video
              </option>

              <option
                value="mixed"
              >
                Mixed Media
              </option>

              <option
                value="generic"
              >
                Generic Video
              </option>
            </select>

            <p
              className="
                text-xs
                text-muted-foreground
              "
            >
              Movies and TV enable semantic
              catalog matching during scans.
            </p>
          </div>

          <div
            className="
              space-y-2
            "
          >
            <Label>
              Management Mode
            </Label>

            <select
              value={
                managementMode
              }
              onChange={
                (
                  event
                ) =>
                  setManagementMode(
                    (
                      event
                        .target
                        .value
                    ) as ManagementMode
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
                value="full_control"
              >
                Full Control
              </option>

              <option
                value="sidecar_only"
              >
                Sidecar Only
              </option>

              <option
                value="read_only"
              >
                Read Only
              </option>
            </select>
          </div>

          <Button
            type="button"
            variant="outline"
            className="
              w-full
            "
            disabled={
              testing
              || !path.trim()
            }
            onClick={
              handleTestStorage
            }
          >
            {
              testing
                ? "Testing..."
                : "Test Storage"
            }
          </Button>

          {storageTest && (
            <div
              className="
                space-y-3
                rounded-md
                border
                p-3
              "
            >
              <div
                className="
                  font-medium
                "
              >
                Storage Test
              </div>

              <div
                className="
                  break-all
                  text-xs
                  text-muted-foreground
                "
              >
                {
                  storageTest.path
                }
              </div>

              <Separator />

              {
                (
                  Object.entries(
                    storageTest
                      .capabilities
                  ) as Array<
                    [
                      keyof StorageTestResult[
                        "capabilities"
                      ],
                      StorageTestResult[
                        "capabilities"
                      ][
                        keyof StorageTestResult[
                          "capabilities"
                        ]
                      ],
                    ]
                  >
                ).map(
                  ([
                    key,
                    capability,
                  ]) => (
                    <div
                      key={key}
                      className="
                        flex
                        gap-2
                        text-sm
                      "
                    >
                      <CapabilityMark
                        status={
                          capability.status
                        }
                      />

                      <span>
                        {
                          capabilityLabels[
                            key
                          ]
                        }
                      </span>
                    </div>
                  )
                )
              }

              <Separator />

              <div
                className="
                  text-sm
                "
              >
                Recommended:
                {" "}

                <strong>
                  {
                    managementModeLabel(
                      storageTest
                        .recommended_management_mode
                    )
                  }
                </strong>
              </div>
            </div>
          )}

          {error && (
            <p
              className="
                text-sm
                text-destructive
              "
            >
              {error}
            </p>
          )}

          <Button
            type="submit"
            className="
              w-full
            "
          >
            Create Library
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
