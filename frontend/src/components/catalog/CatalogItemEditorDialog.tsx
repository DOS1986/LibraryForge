import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ChangeEvent,
  type Dispatch,
  type SetStateAction,
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
  Dialog,
  DialogTitle,
} from "@/components/ui/dialog"

import {
  Input,
} from "@/components/ui/input"

import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"

import {
  ScrollableDialogBody,
  ScrollableDialogContent,
  ScrollableDialogHeader,
} from "@/components/dialogs/ScrollableDialog"

import {
  getCatalogEditorDetail,
  makeCatalogVersionPrimary,
  refreshLibraryArtwork,
  selectCatalogArtwork,
  updateCatalogEditorMetadata,
  updateCatalogVersion,
  updateNfoFile,
  validateNfo,
} from "@/lib/api"

import {
  formatBytes,
  formatDuration,
} from "@/lib/format"

import type {
  CanonicalFieldState,
  CatalogEditorArtwork,
  CatalogEditorDetail,
  CatalogEditorKind,
  CatalogEditorNfoFile,
  CatalogEditorVersion,
} from "@/types"


interface CatalogItemEditorDialogProps {
  kind:
    | CatalogEditorKind
    | null

  id:
    | string
    | null

  onClose:
    () => void

  onChanged?:
    () => Promise<void>
    | void
}


type MetadataForm =
  Record<
    string,
    string
  >


function displayValue(
  value: unknown,
) {
  if (
    value === null
    || value === undefined
    || value === ""
  ) {
    return "—"
  }

  if (Array.isArray(value)) {
    return (
      value.length
        ? value.join(", ")
        : "—"
    )
  }

  if (
    typeof value
    === "object"
  ) {
    return JSON.stringify(
      value
    )
  }

  return String(value)
}


function stringList(
  value: unknown,
) {
  if (!Array.isArray(value)) {
    return ""
  }

  return value
    .map(
      String
    )
    .join(", ")
}


function externalIdsText(
  value: unknown,
) {
  if (
    !value
    || typeof value
    !== "object"
    || Array.isArray(value)
  ) {
    return ""
  }

  return Object.entries(
    value
  )
    .map(
      ([
        key,
        id,
      ]) => (
        `${key}=${String(id)}`
      )
    )
    .join("\n")
}


function parseStringList(
  value: string,
) {
  return value
    .split(",")
    .map(
      item => item.trim()
    )
    .filter(Boolean)
}


function parseExternalIds(
  value: string,
) {
  const result:
    Record<
      string,
      string
    > = {}

  for (
    const line
    of value.split("\n")
  ) {
    const trimmed =
      line.trim()

    if (!trimmed) {
      continue
    }

    const separator =
      trimmed.indexOf("=")

    if (separator < 1) {
      continue
    }

    const key = trimmed
      .slice(
        0,
        separator,
      )
      .trim()

    const id = trimmed
      .slice(
        separator + 1
      )
      .trim()

    if (key && id) {
      result[key] = id
    }
  }

  return result
}


function optionalNumber(
  value: string,
) {
  const trimmed =
    value.trim()

  if (!trimmed) {
    return null
  }

  const parsed =
    Number.parseInt(
      trimmed,
      10,
    )

  return (
    Number.isFinite(parsed)
      ? parsed
      : null
  )
}


function initialForm(
  detail: CatalogEditorDetail,
): MetadataForm {
  const metadata =
    detail.metadata

  const form:
    MetadataForm = {}

  for (
    const [
      key,
      value,
    ] of Object.entries(
      metadata
    )
  ) {
    if (
      key === "genres"
      || key === "studios"
    ) {
      form[key] =
        stringList(value)

      continue
    }

    if (
      key === "external_ids"
    ) {
      form[key] =
        externalIdsText(
          value
        )

      continue
    }

    form[key] = (
      value === null
      || value === undefined
        ? ""
        : String(value)
    )
  }

  form.note = ""

  return form
}


function stateForField(
  states:
    CanonicalFieldState[],
  fieldName: string,
) {
  return states.find(
    state => (
      state.field_name
      === fieldName
    )
  )
}


function FieldLabel({
  label,
  fieldName,
  states,
}: {
  label: string
  fieldName: string
  states: CanonicalFieldState[]
}) {
  const state =
    stateForField(
      states,
      fieldName,
    )

  return (
    <div
      className="
        mb-1.5
        flex
        items-center
        gap-2
        text-sm
        font-medium
      "
    >
      <span>
        {label}
      </span>

      {
        state
        && (
          <Badge
            variant="outline"
            className="
              text-[10px]
            "
          >
            {
              state.source_label
            }

            {
              state.locked
                ? " · locked"
                : ""
            }
          </Badge>
        )
      }
    </div>
  )
}


function TextField({
  label,
  fieldName,
  form,
  setForm,
  states,
  type = "text",
}: {
  label: string
  fieldName: string
  form: MetadataForm
  setForm:
    Dispatch<
      SetStateAction<MetadataForm>
    >
  states: CanonicalFieldState[]
  type?: string
}) {
  return (
    <label
      className="block"
    >
      <FieldLabel
        label={label}
        fieldName={fieldName}
        states={states}
      />

      <Input
        type={type}
        value={
          form[fieldName]
          ?? ""
        }
        onChange={
          event =>
            setForm(
              current => ({
                ...current,
                [fieldName]:
                  event.target.value,
              })
            )
        }
      />
    </label>
  )
}


function TextAreaField({
  label,
  fieldName,
  form,
  setForm,
  states,
  placeholder,
}: {
  label: string
  fieldName: string
  form: MetadataForm
  setForm:
    Dispatch<
      SetStateAction<MetadataForm>
    >
  states: CanonicalFieldState[]
  placeholder?: string
}) {
  return (
    <label
      className="block"
    >
      <FieldLabel
        label={label}
        fieldName={fieldName}
        states={states}
      />

      <textarea
        value={
          form[fieldName]
          ?? ""
        }
        placeholder={placeholder}
        onChange={
          (
            event: ChangeEvent<HTMLTextAreaElement>
          ) =>
            setForm(
              current => ({
                ...current,
                [fieldName]:
                  event.target.value,
              })
            )
        }
        className="
          min-h-24
          w-full
          resize-y
          rounded-md
          border
          bg-background
          px-3
          py-2
          text-sm
        "
      />
    </label>
  )
}


function MetadataEditor({
  detail,
  onSaved,
}: {
  detail: CatalogEditorDetail
  onSaved:
    (
      detail: CatalogEditorDetail
    ) => void
}) {
  const [
    form,
    setForm,
  ] = useState<MetadataForm>(
    () => initialForm(
      detail
    )
  )

  const [
    saving,
    setSaving,
  ] = useState(false)

  const [
    error,
    setError,
  ] = useState<
    string | null
  >(null)


  useEffect(
    () => {
      setForm(
        initialForm(
          detail
        )
      )
    },
    [
      detail,
    ],
  )


  async function save() {
    setSaving(true)
    setError(null)

    try {
      const input:
        Record<
          string,
          unknown
        > = {
          note:
            form.note
            ?? "",
        }

      const copy = (
        ...fields: string[]
      ) => {
        for (
          const field
          of fields
        ) {
          input[field] =
            form[field]
            ?? ""
        }
      }

      if (
        detail.kind
        === "movie"
      ) {
        copy(
          "title",
          "sort_title",
          "original_title",
          "description",
          "tagline",
          "content_rating",
        )

        input.year =
          optionalNumber(
            form.year
            ?? ""
          )

        input.release_date =
          form.release_date
          || null

        input.genres =
          parseStringList(
            form.genres
            ?? ""
          )

        input.studios =
          parseStringList(
            form.studios
            ?? ""
          )

        input.external_ids =
          parseExternalIds(
            form.external_ids
            ?? ""
          )
      }

      if (
        detail.kind
        === "series"
      ) {
        copy(
          "title",
          "sort_title",
          "original_title",
          "description",
          "tagline",
          "content_rating",
        )

        input.start_year =
          optionalNumber(
            form.start_year
            ?? ""
          )

        input.end_year =
          optionalNumber(
            form.end_year
            ?? ""
          )

        input.genres =
          parseStringList(
            form.genres
            ?? ""
          )

        input.studios =
          parseStringList(
            form.studios
            ?? ""
          )

        input.external_ids =
          parseExternalIds(
            form.external_ids
            ?? ""
          )
      }

      if (
        detail.kind
        === "season"
      ) {
        copy(
          "title",
          "description",
        )

        input.external_ids =
          parseExternalIds(
            form.external_ids
            ?? ""
          )
      }

      if (
        detail.kind
        === "episode"
      ) {
        copy(
          "title",
          "sort_title",
          "original_title",
          "description",
          "content_rating",
        )

        input.air_date =
          form.air_date
          || null

        input.absolute_number =
          optionalNumber(
            form.absolute_number
            ?? ""
          )

        input.genres =
          parseStringList(
            form.genres
            ?? ""
          )

        input.studios =
          parseStringList(
            form.studios
            ?? ""
          )

        input.external_ids =
          parseExternalIds(
            form.external_ids
            ?? ""
          )
      }

      const updated =
        await updateCatalogEditorMetadata(
          detail.kind,
          detail.id,
          input,
        )

      onSaved(
        updated
      )

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to save metadata."
      )

    } finally {
      setSaving(false)
    }
  }


  const states =
    detail.field_states


  return (
    <div
      className="
        space-y-5
      "
    >
      <div
        className="
          grid
          gap-4
          md:grid-cols-2
        "
      >
        <TextField
          label={
            detail.kind
            === "episode"
              ? "Episode Title"
              : "Title"
          }
          fieldName="title"
          form={form}
          setForm={setForm}
          states={states}
        />

        {
          detail.kind
          !== "season"
          && (
            <TextField
              label="Sort Title"
              fieldName="sort_title"
              form={form}
              setForm={setForm}
              states={states}
            />
          )
        }

        {
          detail.kind
          !== "season"
          && (
            <TextField
              label="Original Title"
              fieldName="original_title"
              form={form}
              setForm={setForm}
              states={states}
            />
          )
        }

        {
          detail.kind
          === "movie"
          && (
            <>
              <TextField
                label="Year"
                fieldName="year"
                form={form}
                setForm={setForm}
                states={states}
                type="number"
              />

              <TextField
                label="Release Date"
                fieldName="release_date"
                form={form}
                setForm={setForm}
                states={states}
                type="date"
              />
            </>
          )
        }

        {
          detail.kind
          === "series"
          && (
            <>
              <TextField
                label="Start Year"
                fieldName="start_year"
                form={form}
                setForm={setForm}
                states={states}
                type="number"
              />

              <TextField
                label="End Year"
                fieldName="end_year"
                form={form}
                setForm={setForm}
                states={states}
                type="number"
              />
            </>
          )
        }

        {
          detail.kind
          === "episode"
          && (
            <>
              <TextField
                label="Air Date"
                fieldName="air_date"
                form={form}
                setForm={setForm}
                states={states}
                type="date"
              />

              <TextField
                label="Absolute Number"
                fieldName="absolute_number"
                form={form}
                setForm={setForm}
                states={states}
                type="number"
              />
            </>
          )
        }

        {
          detail.kind
          !== "season"
          && (
            <TextField
              label="Content Rating"
              fieldName="content_rating"
              form={form}
              setForm={setForm}
              states={states}
            />
          )
        }

        {
          (
            detail.kind
            === "movie"
            || detail.kind
            === "series"
          )
          && (
            <TextAreaField
              label="Tagline"
              fieldName="tagline"
              form={form}
              setForm={setForm}
              states={states}
            />
          )
        }
      </div>

      <TextAreaField
        label="Overview / Description"
        fieldName="description"
        form={form}
        setForm={setForm}
        states={states}
      />

      {
        detail.kind
        !== "season"
        && (
          <div
            className="
              grid
              gap-4
              md:grid-cols-2
            "
          >
            <TextAreaField
              label="Genres"
              fieldName="genres"
              form={form}
              setForm={setForm}
              states={states}
              placeholder="Science Fiction, Drama"
            />

            <TextAreaField
              label="Studios"
              fieldName="studios"
              form={form}
              setForm={setForm}
              states={states}
              placeholder="Studio A, Studio B"
            />
          </div>
        )
      }

      <TextAreaField
        label="External IDs"
        fieldName="external_ids"
        form={form}
        setForm={setForm}
        states={states}
        placeholder={
          "tmdb=12345\nimdb=tt1234567"
        }
      />

      <label
        className="block"
      >
        <div
          className="
            mb-1.5
            text-sm
            font-medium
          "
        >
          Change Note
        </div>

        <Input
          value={
            form.note
            ?? ""
          }
          onChange={
            event =>
              setForm(
                current => ({
                  ...current,
                  note:
                    event.target.value,
                })
              )
          }
          placeholder="Optional reason for this edit"
        />
      </label>

      {
        error
        && (
          <div
            className="
              rounded-md
              border
              border-destructive/40
              bg-destructive/5
              p-3
              text-sm
              text-destructive
            "
          >
            {error}
          </div>
        )
      }

      <div
        className="
          flex
          justify-end
        "
      >
        <Button
          type="button"
          disabled={saving}
          onClick={
            () => void save()
          }
        >
          {
            saving
              ? "Saving..."
              : "Save Canonical Metadata"
          }
        </Button>
      </div>
    </div>
  )
}


function VersionEditor({
  version,
  onChanged,
}: {
  version: CatalogEditorVersion
  onChanged: () => Promise<void>
}) {
  const [
    name,
    setName,
  ] = useState(
    version.name
  )

  const [
    edition,
    setEdition,
  ] = useState(
    version.edition
  )

  const [
    notes,
    setNotes,
  ] = useState(
    version.notes
  )

  const [
    busy,
    setBusy,
  ] = useState(false)


  useEffect(
    () => {
      setName(
        version.name
      )
      setEdition(
        version.edition
      )
      setNotes(
        version.notes
      )
    },
    [
      version,
    ],
  )


  async function save() {
    setBusy(true)

    try {
      await updateCatalogVersion(
        version.id,
        {
          name,
          edition,
          notes,
          note:
            "Updated version metadata.",
        },
      )

      await onChanged()

    } finally {
      setBusy(false)
    }
  }


  async function makePrimary() {
    setBusy(true)

    try {
      await makeCatalogVersionPrimary(
        version.id
      )

      await onChanged()

    } finally {
      setBusy(false)
    }
  }


  return (
    <Card>
      <CardHeader>
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
            <CardTitle
              className="text-base"
            >
              {version.name}
            </CardTitle>

            <CardDescription
              className="
                mt-1
                break-all
              "
            >
              {
                version.relative_path
              }
            </CardDescription>
          </div>

          {
            version.is_primary
            && (
              <Badge>
                Primary
              </Badge>
            )
          }
        </div>
      </CardHeader>

      <CardContent
        className="space-y-4"
      >
        <div
          className="
            grid
            gap-3
            text-sm
            md:grid-cols-4
          "
        >
          <div>
            <div
              className="text-muted-foreground"
            >
              Size
            </div>
            <div>
              {
                formatBytes(
                  version.size_bytes
                )
              }
            </div>
          </div>

          <div>
            <div
              className="text-muted-foreground"
            >
              Runtime
            </div>
            <div>
              {
                formatDuration(
                  version.duration_seconds
                )
              }
            </div>
          </div>

          <div>
            <div
              className="text-muted-foreground"
            >
              Video
            </div>
            <div>
              {
                version.video_codec
                || "—"
              }
              {
                version.width
                && version.height
                  ? (
                    ` · ${version.width}`
                    + `×${version.height}`
                  )
                  : ""
              }
            </div>
          </div>

          <div>
            <div
              className="text-muted-foreground"
            >
              Audio
            </div>
            <div>
              {
                version.audio_codec
                || "—"
              }
              {
                version.audio_channels
                  ? (
                    ` · ${version.audio_channels}ch`
                  )
                  : ""
              }
            </div>
          </div>
        </div>

        <div
          className="
            grid
            gap-4
            md:grid-cols-2
          "
        >
          <label>
            <div
              className="
                mb-1.5
                text-sm
                font-medium
              "
            >
              Version Name
            </div>
            <Input
              value={name}
              onChange={
                event =>
                  setName(
                    event.target.value
                  )
              }
            />
          </label>

          <label>
            <div
              className="
                mb-1.5
                text-sm
                font-medium
              "
            >
              Edition
            </div>
            <Input
              value={edition}
              onChange={
                event =>
                  setEdition(
                    event.target.value
                  )
              }
            />
          </label>
        </div>

        <label
          className="block"
        >
          <div
            className="
              mb-1.5
              text-sm
              font-medium
            "
          >
            Notes
          </div>
          <textarea
            value={notes}
            onChange={
              (
                event: ChangeEvent<HTMLTextAreaElement>
              ) =>
                setNotes(
                  event.target.value
                )
            }
            className="
              min-h-20
              w-full
              resize-y
              rounded-md
              border
              bg-background
              px-3
              py-2
              text-sm
            "
          />
        </label>

        <div
          className="
            flex
            flex-wrap
            gap-2
          "
        >
          <Button
            type="button"
            disabled={busy}
            onClick={
              () => void save()
            }
          >
            Save Version
          </Button>

          {
            !version.is_primary
            && (
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={
                  () => void makePrimary()
                }
              >
                Make Primary
              </Button>
            )
          }
        </div>
      </CardContent>
    </Card>
  )
}


function SourcesTab({
  detail,
}: {
  detail: CatalogEditorDetail
}) {
  if (
    detail.sources.length
    === 0
  ) {
    return (
      <div
        className="
          rounded-md
          border
          p-5
          text-sm
          text-muted-foreground
        "
      >
        No direct source records are attached
        to this semantic item yet. Series and
        Season source aggregation will be added
        when series-level NFO/provider ingestion
        is implemented.
      </div>
    )
  }

  return (
    <div
      className="space-y-3"
    >
      {
        detail.sources.map(
          source => (
            <details
              key={source.id}
              className="
                rounded-md
                border
                p-4
              "
            >
              <summary
                className="
                  cursor-pointer
                  font-medium
                "
              >
                {
                  source.source_type_label
                }
                {" · "}
                {
                  source.file_name
                }
                {" · "}
                {
                  source.status_label
                }
              </summary>

              <div
                className="
                  mt-3
                  break-all
                  text-xs
                  text-muted-foreground
                "
              >
                {
                  source.relative_path
                }
              </div>

              <pre
                className="
                  mt-3
                  max-h-80
                  overflow-auto
                  rounded-md
                  bg-muted
                  p-3
                  text-xs
                "
              >
                {
                  JSON.stringify(
                    source.extracted_data,
                    null,
                    2,
                  )
                }
              </pre>
            </details>
          )
        )
      }
    </div>
  )
}


function NfoTab({
  detail,
  onChanged,
}: {
  detail: CatalogEditorDetail
  onChanged: () => Promise<void>
}) {
  const [
    selected,
    setSelected,
  ] = useState<
    CatalogEditorNfoFile | null
  >(
    detail.nfo_files[0]
    ?? null
  )

  const [
    xml,
    setXml,
  ] = useState(
    selected?.raw_xml
    ?? ""
  )

  const [
    busy,
    setBusy,
  ] = useState(false)

  const [
    message,
    setMessage,
  ] = useState<
    string | null
  >(null)


  useEffect(
    () => {
      const next = (
        selected
        ? detail.nfo_files.find(
          item => (
            item.id
            === selected.id
          )
        )
        : detail.nfo_files[0]
      )

      setSelected(
        next
        ?? null
      )

      setXml(
        next?.raw_xml
        ?? ""
      )
    },
    [
      detail.nfo_files,
    ],
  )


  if (
    detail.nfo_files.length
    === 0
  ) {
    return (
      <div
        className="
          rounded-md
          border
          p-5
          text-sm
          text-muted-foreground
        "
      >
        No directly associated NFO file was
        indexed for this item.
      </div>
    )
  }


  async function validate() {
    setBusy(true)
    setMessage(null)

    try {
      const result =
        await validateNfo(
          xml
        )

      setMessage(
        result.valid
          ? (
            `Valid ${result.root_element} NFO.`
          )
          : (
            result.error
            || "NFO is invalid."
          )
      )

    } catch (err) {
      setMessage(
        err instanceof Error
          ? err.message
          : "Unable to validate NFO."
      )

    } finally {
      setBusy(false)
    }
  }


  async function save() {
    if (!selected) {
      return
    }

    setBusy(true)
    setMessage(null)

    try {
      await updateNfoFile(
        selected.id,
        xml,
      )

      setMessage(
        "NFO saved."
      )

      await onChanged()

    } catch (err) {
      setMessage(
        err instanceof Error
          ? err.message
          : "Unable to save NFO."
      )

    } finally {
      setBusy(false)
    }
  }


  return (
    <div
      className="space-y-4"
    >
      <div
        className="
          flex
          flex-wrap
          gap-2
        "
      >
        {
          detail.nfo_files.map(
            nfo => (
              <Button
                key={nfo.id}
                type="button"
                variant={
                  selected?.id
                  === nfo.id
                    ? "default"
                    : "outline"
                }
                onClick={
                  () => {
                    setSelected(nfo)
                    setXml(
                      nfo.raw_xml
                    )
                    setMessage(null)
                  }
                }
              >
                {nfo.file_name}
              </Button>
            )
          )
        }
      </div>

      {
        selected
        && (
          <>
            <div
              className="
                flex
                flex-wrap
                gap-2
                text-xs
                text-muted-foreground
              "
            >
              <span>
                {
                  selected.relative_path
                }
              </span>
              <span>
                {
                  selected.root_element
                  || "unknown root"
                }
              </span>
              <span>
                {
                  selected.parse_status
                }
              </span>
            </div>

            <textarea
              value={xml}
              onChange={
                (
                  event: ChangeEvent<HTMLTextAreaElement>
                ) =>
                  setXml(
                    event.target.value
                  )
              }
              spellCheck={false}
              className="
                min-h-[420px]
                w-full
                resize-y
                rounded-md
                border
                bg-background
                p-3
                font-mono
                text-xs
              "
            />

            <div
              className="
                flex
                flex-wrap
                items-center
                gap-2
              "
            >
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={
                  () => void validate()
                }
              >
                Validate
              </Button>

              <Button
                type="button"
                disabled={busy}
                onClick={
                  () => void save()
                }
              >
                Save NFO
              </Button>

              {
                message
                && (
                  <span
                    className="text-sm"
                  >
                    {message}
                  </span>
                )
              }
            </div>
          </>
        )
      }
    </div>
  )
}



function ArtworkCard({
  artwork,
  busy,
  onSelect,
}: {
  artwork: CatalogEditorArtwork
  busy: boolean
  onSelect: () => void
}) {
  return (
    <Card
      className={
        artwork.is_selected
          ? "ring-2 ring-primary/40"
          : ""
      }
    >
      <div
        className="
          aspect-[16/10]
          overflow-hidden
          rounded-t-lg
          bg-muted
        "
      >
        <img
          src={artwork.content_url}
          alt={artwork.file_name}
          loading="lazy"
          className="
            h-full
            w-full
            object-contain
          "
        />
      </div>

      <CardContent
        className="
          space-y-3
          pt-4
        "
      >
        <div
          className="
            flex
            items-start
            justify-between
            gap-2
          "
        >
          <div
            className="min-w-0"
          >
            <div
              className="
                truncate
                text-sm
                font-medium
              "
              title={artwork.file_name}
            >
              {artwork.file_name}
            </div>

            <div
              className="
                mt-1
                truncate
                text-xs
                text-muted-foreground
              "
              title={artwork.relative_path}
            >
              {artwork.relative_path}
            </div>
          </div>

          {
            artwork.is_selected
            && (
              <Badge>
                Preferred
              </Badge>
            )
          }
        </div>

        <div
          className="
            flex
            items-center
            justify-between
            gap-3
            text-xs
            text-muted-foreground
          "
        >
          <span>
            {artwork.source_name}
          </span>

          <span>
            {formatBytes(artwork.size_bytes)}
          </span>
        </div>

        {
          !artwork.is_selected
          && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={onSelect}
              className="w-full"
            >
              Use as Preferred
            </Button>
          )
        }
      </CardContent>
    </Card>
  )
}


function ArtworkTab({
  detail,
  onChanged,
}: {
  detail: CatalogEditorDetail
  onChanged: () => Promise<void>
}) {
  const [busyId, setBusyId] = useState<
    string | null
  >(null)

  const [refreshing, setRefreshing] =
    useState(false)

  const [error, setError] = useState<
    string | null
  >(null)

  const artworkTypes = [
    "primary",
    "backdrop",
    "banner",
    "logo",
    "thumb",
  ] as const

  async function choose(
    artwork: CatalogEditorArtwork,
  ) {
    setBusyId(artwork.id)
    setError(null)

    try {
      await selectCatalogArtwork(
        artwork.id
      )

      await onChanged()

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to select artwork."
      )

    } finally {
      setBusyId(null)
    }
  }

  async function refresh() {
    setRefreshing(true)
    setError(null)

    try {
      await refreshLibraryArtwork(
        detail.library_id
      )

      await onChanged()

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to refresh artwork."
      )

    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div
      className="space-y-6"
    >
      <div
        className="
          flex
          flex-wrap
          items-center
          justify-between
          gap-3
        "
      >
        <div>
          <h3
            className="font-semibold"
          >
            Local Artwork
          </h3>

          <p
            className="
              mt-1
              text-sm
              text-muted-foreground
            "
          >
            LibraryForge indexes existing
            sidecar artwork without modifying
            the source files.
          </p>
        </div>

        <Button
          type="button"
          variant="outline"
          disabled={refreshing}
          onClick={
            () => void refresh()
          }
        >
          {
            refreshing
              ? "Refreshing..."
              : "Refresh Local Artwork"
          }
        </Button>
      </div>

      {
        error
        && (
          <div
            className="
              rounded-md
              border
              border-destructive/40
              bg-destructive/5
              p-3
              text-sm
              text-destructive
            "
          >
            {error}
          </div>
        )
      }

      {
        detail.artwork.length === 0
        && (
          <Card>
            <CardContent
              className="
                py-10
                text-center
                text-sm
                text-muted-foreground
              "
            >
              No recognized local artwork was
              found for this catalog item.
            </CardContent>
          </Card>
        )
      }

      {
        artworkTypes.map(
          artworkType => {
            const items =
              detail.artwork.filter(
                artwork => (
                  artwork.artwork_type
                  === artworkType
                )
              )

            if (!items.length) {
              return null
            }

            return (
              <section
                key={artworkType}
                className="space-y-3"
              >
                <h4
                  className="
                    capitalize
                    font-medium
                  "
                >
                  {artworkType}
                </h4>

                <div
                  className="
                    grid
                    gap-4
                    sm:grid-cols-2
                    xl:grid-cols-3
                  "
                >
                  {
                    items.map(
                      artwork => (
                        <ArtworkCard
                          key={artwork.id}
                          artwork={artwork}
                          busy={
                            busyId
                            === artwork.id
                          }
                          onSelect={
                            () =>
                              void choose(
                                artwork
                              )
                          }
                        />
                      )
                    )
                  }
                </div>
              </section>
            )
          }
        )
      }
    </div>
  )
}


function HistoryTab({
  detail,
}: {
  detail: CatalogEditorDetail
}) {
  if (
    detail.history.length
    === 0
  ) {
    return (
      <div
        className="
          rounded-md
          border
          p-5
          text-sm
          text-muted-foreground
        "
      >
        No canonical metadata changes have been
        recorded yet.
      </div>
    )
  }

  return (
    <div
      className="space-y-3"
    >
      {
        detail.history.map(
          change => (
            <Card
              key={change.id}
            >
              <CardHeader
                className="pb-3"
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
                    <CardTitle
                      className="text-sm"
                    >
                      {
                        change.source_label
                      }
                      {" metadata change"}
                    </CardTitle>

                    <CardDescription>
                      {
                        new Date(
                          change.created_at
                        ).toLocaleString()
                      }
                      {
                        change.changed_by_label
                          ? (
                            ` · ${change.changed_by_label}`
                          )
                          : ""
                      }
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>

              <CardContent
                className="space-y-2"
              >
                {
                  Object.entries(
                    change.changes
                  ).map(
                    ([
                      field,
                      values,
                    ]) => (
                      <div
                        key={field}
                        className="
                          rounded-md
                          border
                          p-3
                          text-sm
                        "
                      >
                        <div
                          className="font-medium"
                        >
                          {field}
                        </div>

                        <div
                          className="
                            mt-1
                            text-xs
                            text-muted-foreground
                          "
                        >
                          {
                            displayValue(
                              values.old
                            )
                          }
                          {" → "}
                          {
                            displayValue(
                              values.new
                            )
                          }
                        </div>
                      </div>
                    )
                  )
                }

                {
                  change.note
                  && (
                    <div
                      className="
                        text-sm
                        text-muted-foreground
                      "
                    >
                      {change.note}
                    </div>
                  )
                }
              </CardContent>
            </Card>
          )
        )
      }
    </div>
  )
}


export function CatalogItemEditorDialog({
  kind,
  id,
  onClose,
  onChanged,
}: CatalogItemEditorDialogProps) {
  const [
    detail,
    setDetail,
  ] = useState<
    CatalogEditorDetail | null
  >(null)

  const [
    loading,
    setLoading,
  ] = useState(false)

  const [
    error,
    setError,
  ] = useState<
    string | null
  >(null)


  const load =
    useCallback(
      async () => {
        if (!kind || !id) {
          return
        }

        setLoading(true)
        setError(null)

        try {
          const result =
            await getCatalogEditorDetail(
              kind,
              id,
            )

          setDetail(
            result
          )

        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load catalog item."
          )

        } finally {
          setLoading(false)
        }
      },
      [
        kind,
        id,
      ],
    )


  useEffect(
    () => {
      setDetail(null)

      if (kind && id) {
        void load()
      }
    },
    [
      kind,
      id,
      load,
    ],
  )


  const title =
    useMemo(
      () => {
        if (!detail) {
          return "Canonical Metadata"
        }

        const base =
          String(
            detail.metadata.title
            ?? "Untitled"
          )

        if (
          detail.kind
          === "episode"
          && detail.context
        ) {
          return (
            `${detail.context.series_title || "Series"} · `
            + `S${String(
              detail.context.season_number
              ?? 0
            ).padStart(2, "0")}`
            + `E${String(
              detail.context.episode_number
              ?? 0
            ).padStart(2, "0")}`
            + ` · ${base}`
          )
        }

        return base
      },
      [
        detail,
      ],
    )


  async function refreshAfterChange() {
    await load()

    await onChanged?.()
  }


  return (
    <Dialog
      open={
        Boolean(
          kind
          && id
        )
      }
      onOpenChange={
        open => {
          if (!open) {
            onClose()
          }
        }
      }
    >
      <ScrollableDialogContent
        className="
          !max-w-[1500px]
          sm:!max-w-[1500px]
        "
      >
        <ScrollableDialogHeader>
          <div
            className="
              flex
              flex-wrap
              items-start
              justify-between
              gap-3
              pr-4
            "
          >
            <div>
              <DialogTitle>
                {title}
              </DialogTitle>

              {
                detail?.semantic_key
                && (
                  <div
                    className="
                      mt-1
                      break-all
                      font-mono
                      text-xs
                      text-muted-foreground
                    "
                  >
                    {
                      detail.semantic_key
                    }
                  </div>
                )
              }
            </div>

            <div
              className="
                flex
                gap-2
              "
            >
              <Badge
                variant="outline"
              >
                {
                  detail?.kind
                  ?? kind
                  ?? "catalog"
                }
              </Badge>

              {
                detail?.semantic_locked
                && (
                  <Badge>
                    Semantic Locked
                  </Badge>
                )
              }
            </div>
          </div>
        </ScrollableDialogHeader>

        <ScrollableDialogBody>
          {
            loading
            && !detail
            && (
              <div
                className="
                  p-10
                  text-center
                  text-muted-foreground
                "
              >
                Loading canonical metadata...
              </div>
            )
          }

          {
            error
            && (
              <div
                className="
                  rounded-md
                  border
                  border-destructive/40
                  bg-destructive/5
                  p-4
                  text-destructive
                "
              >
                {error}
              </div>
            )
          }

          {
            detail
            && (
              <Tabs
                defaultValue="overview"
              >
                <TabsList
                  className="
                    h-auto
                    flex-wrap
                  "
                >
                  <TabsTrigger
                    value="overview"
                  >
                    Overview
                  </TabsTrigger>

                  <TabsTrigger
                    value="metadata"
                  >
                    Metadata
                  </TabsTrigger>

                  {
                    detail.versions.length
                    > 0
                    && (
                      <TabsTrigger
                        value="versions"
                      >
                        Versions
                      </TabsTrigger>
                    )
                  }

                  <TabsTrigger
                    value="sources"
                  >
                    Sources
                  </TabsTrigger>

                  <TabsTrigger
                    value="artwork"
                  >
                    Artwork
                  </TabsTrigger>

                  <TabsTrigger
                    value="nfo"
                  >
                    NFO
                  </TabsTrigger>

                  <TabsTrigger
                    value="history"
                  >
                    History
                  </TabsTrigger>
                </TabsList>

                <TabsContent
                  value="overview"
                  className="
                    mt-5
                    space-y-5
                  "
                >
                  <div
                    className="
                      grid
                      gap-4
                      md:grid-cols-3
                    "
                  >
                    <Card>
                      <CardHeader>
                        <CardDescription>
                          Type
                        </CardDescription>
                        <CardTitle>
                          {detail.kind}
                        </CardTitle>
                      </CardHeader>
                    </Card>

                    <Card>
                      <CardHeader>
                        <CardDescription>
                          Versions
                        </CardDescription>
                        <CardTitle>
                          {
                            detail.versions.length
                          }
                        </CardTitle>
                      </CardHeader>
                    </Card>

                    <Card>
                      <CardHeader>
                        <CardDescription>
                          Manual Fields
                        </CardDescription>
                        <CardTitle>
                          {
                            detail.field_states
                              .filter(
                                state => (
                                  state.source
                                  === "manual"
                                )
                              )
                              .length
                          }
                        </CardTitle>
                      </CardHeader>
                    </Card>
                  </div>

                  <Card>
                    <CardHeader>
                      <CardTitle
                        className="text-base"
                      >
                        Canonical Snapshot
                      </CardTitle>
                    </CardHeader>

                    <CardContent>
                      <div
                        className="
                          grid
                          gap-x-8
                          gap-y-4
                          md:grid-cols-2
                        "
                      >
                        {
                          Object.entries(
                            detail.metadata
                          ).map(
                            ([
                              key,
                              value,
                            ]) => (
                              <div
                                key={key}
                              >
                                <div
                                  className="
                                    text-xs
                                    uppercase
                                    tracking-wide
                                    text-muted-foreground
                                  "
                                >
                                  {
                                    key.replaceAll(
                                      "_",
                                      " ",
                                    )
                                  }
                                </div>

                                <div
                                  className="
                                    mt-1
                                    whitespace-pre-wrap
                                    text-sm
                                  "
                                >
                                  {
                                    displayValue(
                                      value
                                    )
                                  }
                                </div>
                              </div>
                            )
                          )
                        }
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent
                  value="metadata"
                  className="mt-5"
                >
                  <MetadataEditor
                    detail={detail}
                    onSaved={
                      updated => {
                        setDetail(
                          updated
                        )

                        void onChanged?.()
                      }
                    }
                  />
                </TabsContent>

                <TabsContent
                  value="versions"
                  className="
                    mt-5
                    space-y-4
                  "
                >
                  {
                    detail.versions.map(
                      version => (
                        <VersionEditor
                          key={version.id}
                          version={version}
                          onChanged={
                            refreshAfterChange
                          }
                        />
                      )
                    )
                  }
                </TabsContent>

                <TabsContent
                  value="sources"
                  className="mt-5"
                >
                  <SourcesTab
                    detail={detail}
                  />
                </TabsContent>

                <TabsContent
                  value="artwork"
                  className="mt-5"
                >
                  <ArtworkTab
                    detail={detail}
                    onChanged={
                      refreshAfterChange
                    }
                  />
                </TabsContent>

                <TabsContent
                  value="nfo"
                  className="mt-5"
                >
                  <NfoTab
                    detail={detail}
                    onChanged={
                      refreshAfterChange
                    }
                  />
                </TabsContent>

                <TabsContent
                  value="history"
                  className="mt-5"
                >
                  <HistoryTab
                    detail={detail}
                  />
                </TabsContent>
              </Tabs>
            )
          }
        </ScrollableDialogBody>
      </ScrollableDialogContent>
    </Dialog>
  )
}
