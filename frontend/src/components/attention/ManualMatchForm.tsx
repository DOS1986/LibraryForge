import {
  useEffect,
  useState,
  type FormEvent,
} from "react"

import {
  Button,
} from "@/components/ui/button"

import {
  Input,
} from "@/components/ui/input"

import {
  Label,
} from "@/components/ui/label"

import type {
  Library,
  SemanticCandidate,
  SemanticResolveInput,
} from "@/types"


interface ManualMatchFormProps {
  library: Library

  seed:
    SemanticCandidate
    | null

  busy?: boolean

  onSubmit:
    (
      input: SemanticResolveInput
    ) => Promise<void>
}


function optionalInteger(
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
    Number.isFinite(
      parsed
    )
      ? parsed
      : null
  )
}


export function ManualMatchForm({
  library,
  seed,
  busy = false,
  onSubmit,
}: ManualMatchFormProps) {
  const defaultKind:
    | "movie"
    | "episode" = (
      seed?.kind
      === "episode"
        ? "episode"
        : seed?.kind
          === "movie"
          ? "movie"
          : library.content_type
            === "tv"
            ? "episode"
            : "movie"
    )

  const [
    kind,
    setKind,
  ] = useState<
    | "movie"
    | "episode"
  >(
    defaultKind
  )

  const [
    title,
    setTitle,
  ] = useState("")

  const [
    year,
    setYear,
  ] = useState("")

  const [
    edition,
    setEdition,
  ] = useState("")

  const [
    seriesTitle,
    setSeriesTitle,
  ] = useState("")

  const [
    seriesYear,
    setSeriesYear,
  ] = useState("")

  const [
    seasonNumber,
    setSeasonNumber,
  ] = useState("")

  const [
    episodeNumber,
    setEpisodeNumber,
  ] = useState("")

  const [
    episodeEndNumber,
    setEpisodeEndNumber,
  ] = useState("")

  const [
    episodeTitle,
    setEpisodeTitle,
  ] = useState("")

  const [
    lock,
    setLock,
  ] = useState(true)

  const [
    notes,
    setNotes,
  ] = useState("")


  useEffect(
    () => {
      const nextKind:
        | "movie"
        | "episode" = (
          seed?.kind
          === "episode"
            ? "episode"
            : seed?.kind
              === "movie"
              ? "movie"
              : library.content_type
                === "tv"
                ? "episode"
                : "movie"
        )

      setKind(
        nextKind
      )

      setTitle(
        seed?.title
        ?? ""
      )

      setYear(
        seed?.year
        ? String(
          seed.year
        )
        : ""
      )

      setEdition(
        seed?.edition
        ?? ""
      )

      setSeriesTitle(
        seed?.series_title
        ?? ""
      )

      setSeriesYear(
        seed?.series_year
        ? String(
          seed.series_year
        )
        : ""
      )

      setSeasonNumber(
        seed?.season_number
        !== null
        && seed?.season_number
        !== undefined
          ? String(
            seed.season_number
          )
          : ""
      )

      setEpisodeNumber(
        seed?.episode_number
        !== null
        && seed?.episode_number
        !== undefined
          ? String(
            seed.episode_number
          )
          : ""
      )

      setEpisodeEndNumber(
        seed?.episode_end_number
        !== null
        && seed?.episode_end_number
        !== undefined
          ? String(
            seed.episode_end_number
          )
          : ""
      )

      setEpisodeTitle(
        seed?.episode_title
        || (
          seed?.kind
          === "episode"
            ? seed.title
            : ""
        )
        || ""
      )

      setLock(true)
      setNotes("")
    },
    [
      library.content_type,
      seed,
    ],
  )


  async function submit(
    event: FormEvent,
  ) {
    event.preventDefault()

    if (kind === "movie") {
      await onSubmit({
        candidate_source:
          "manual",

        lock,

        notes,

        kind:
          "movie",

        title:
          title.trim(),

        year:
          optionalInteger(
            year
          ),

        edition:
          edition.trim(),
      })

      return
    }

    await onSubmit({
      candidate_source:
        "manual",

      lock,

      notes,

      kind:
        "episode",

      series_title:
        seriesTitle.trim(),

      series_year:
        optionalInteger(
          seriesYear
        ),

      season_number:
        optionalInteger(
          seasonNumber
        ),

      episode_number:
        optionalInteger(
          episodeNumber
        ),

      episode_end_number:
        optionalInteger(
          episodeEndNumber
        ),

      episode_title:
        episodeTitle.trim(),
    })
  }


  return (
    <form
      onSubmit={
        submit
      }
      className="
        space-y-5
      "
    >
      <div
        className="
          space-y-2
        "
      >
        <Label>
          Match As
        </Label>

        <select
          value={
            kind
          }
          onChange={
            (
              event
            ) =>
              setKind(
                (
                  event
                    .target
                    .value
                ) as
                  | "movie"
                  | "episode"
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
            value="movie"
          >
            Movie
          </option>

          <option
            value="episode"
          >
            TV Episode
          </option>
        </select>
      </div>

      {
        kind === "movie"
          ? (
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
                  md:col-span-2
                "
              >
                <Label>
                  Movie Title
                </Label>

                <Input
                  value={title}
                  onChange={
                    (
                      event
                    ) =>
                      setTitle(
                        event
                          .target
                          .value
                      )
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
                  Year
                </Label>

                <Input
                  value={year}
                  onChange={
                    (
                      event
                    ) =>
                      setYear(
                        event
                          .target
                          .value
                      )
                  }
                  inputMode="numeric"
                  placeholder="1982"
                />
              </div>

              <div
                className="
                  space-y-2
                "
              >
                <Label>
                  Edition
                </Label>

                <Input
                  value={edition}
                  onChange={
                    (
                      event
                    ) =>
                      setEdition(
                        event
                          .target
                          .value
                      )
                  }
                  placeholder="Final Cut"
                />
              </div>
            </div>
          )
          : (
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
                  md:col-span-2
                "
              >
                <Label>
                  Series Title
                </Label>

                <Input
                  value={
                    seriesTitle
                  }
                  onChange={
                    (
                      event
                    ) =>
                      setSeriesTitle(
                        event
                          .target
                          .value
                      )
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
                  Series Year
                </Label>

                <Input
                  value={
                    seriesYear
                  }
                  onChange={
                    (
                      event
                    ) =>
                      setSeriesYear(
                        event
                          .target
                          .value
                      )
                  }
                  inputMode="numeric"
                  placeholder="2015"
                />
              </div>

              <div />

              <div
                className="
                  space-y-2
                "
              >
                <Label>
                  Season Number
                </Label>

                <Input
                  value={
                    seasonNumber
                  }
                  onChange={
                    (
                      event
                    ) =>
                      setSeasonNumber(
                        event
                          .target
                          .value
                      )
                  }
                  inputMode="numeric"
                  required
                />
              </div>

              <div
                className="
                  space-y-2
                "
              >
                <Label>
                  Episode Number
                </Label>

                <Input
                  value={
                    episodeNumber
                  }
                  onChange={
                    (
                      event
                    ) =>
                      setEpisodeNumber(
                        event
                          .target
                          .value
                      )
                  }
                  inputMode="numeric"
                  required
                />
              </div>

              <div
                className="
                  space-y-2
                "
              >
                <Label>
                  Ending Episode
                </Label>

                <Input
                  value={
                    episodeEndNumber
                  }
                  onChange={
                    (
                      event
                    ) =>
                      setEpisodeEndNumber(
                        event
                          .target
                          .value
                      )
                  }
                  inputMode="numeric"
                  placeholder="Optional"
                />
              </div>

              <div
                className="
                  space-y-2
                "
              >
                <Label>
                  Episode Title
                </Label>

                <Input
                  value={
                    episodeTitle
                  }
                  onChange={
                    (
                      event
                    ) =>
                      setEpisodeTitle(
                        event
                          .target
                          .value
                      )
                  }
                  placeholder="Optional"
                />
              </div>
            </div>
          )
      }

      <div
        className="
          space-y-2
        "
      >
        <Label>
          Notes
        </Label>

        <textarea
          value={
            notes
          }
          onChange={
            (
              event
            ) =>
              setNotes(
                event
                  .target
                  .value
              )
          }
          className="
            min-h-20
            w-full
            resize-y
            rounded-md
            border
            bg-background
            p-3
            text-sm
          "
          placeholder="Optional note about this decision"
        />
      </div>

      <label
        className="
          flex
          cursor-pointer
          items-start
          gap-3
          rounded-md
          border
          p-3
        "
      >
        <input
          type="checkbox"
          checked={
            lock
          }
          onChange={
            (
              event
            ) =>
              setLock(
                event
                  .target
                  .checked
              )
          }
          className="
            mt-1
          "
        />

        <span>
          <span
            className="
              block
              font-medium
            "
          >
            Lock this decision
          </span>

          <span
            className="
              block
              text-xs
              text-muted-foreground
            "
          >
            Future scans will not replace
            this file's confirmed semantic
            match until it is unlocked.
          </span>
        </span>
      </label>

      <Button
        type="submit"
        disabled={
          busy
        }
      >
        {
          busy
            ? "Saving..."
            : lock
              ? "Resolve & Lock"
              : "Resolve"
        }
      </Button>
    </form>
  )
}
