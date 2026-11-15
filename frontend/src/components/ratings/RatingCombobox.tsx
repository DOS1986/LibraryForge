import {
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react"

import { Input } from "@/components/ui/input"


interface RatingOption {
  value: string
  meaning: string
  group: "TV" | "Movies" | "Other"
}

const TV_OPTIONS: RatingOption[] = [
  { value: "TV-Y", meaning: "All children", group: "TV" },
  { value: "TV-Y7", meaning: "Directed to older children (7+)", group: "TV" },
  { value: "TV-Y7-FV", meaning: "Older children, fantasy violence", group: "TV" },
  { value: "TV-G", meaning: "General audience", group: "TV" },
  { value: "TV-PG", meaning: "Parental guidance suggested", group: "TV" },
  { value: "TV-14", meaning: "Parents strongly cautioned (14+)", group: "TV" },
  { value: "TV-MA", meaning: "Mature audience only", group: "TV" },
]

const MOVIE_OPTIONS: RatingOption[] = [
  { value: "G", meaning: "General audiences", group: "Movies" },
  { value: "PG", meaning: "Parental guidance suggested", group: "Movies" },
  { value: "PG-13", meaning: "Parents strongly cautioned (13+)", group: "Movies" },
  { value: "R", meaning: "Restricted (under 17 with a parent)", group: "Movies" },
  { value: "NC-17", meaning: "Adults only", group: "Movies" },
]

const OTHER_OPTIONS: RatingOption[] = [
  { value: "NR", meaning: "Not rated", group: "Other" },
]


function ratingOptions(prefer: "tv" | "movie"): RatingOption[] {
  return prefer === "tv"
    ? [...TV_OPTIONS, ...MOVIE_OPTIONS, ...OTHER_OPTIONS]
    : [...MOVIE_OPTIONS, ...TV_OPTIONS, ...OTHER_OPTIONS]
}


/**
 * A text field for a content rating with a list of standard ratings that
 * narrows as you type. Any value can still be typed (for example a rating
 * from another country).
 */
export function RatingCombobox({
  value,
  onChange,
  prefer = "movie",
  id,
  disabled = false,
}: {
  value: string
  onChange: (value: string) => void
  prefer?: "tv" | "movie"
  id?: string
  disabled?: boolean
}) {
  const generatedId = useId()
  const inputId = id ?? `rating-${generatedId}`
  const listId = `${inputId}-options`
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const blurTimer = useRef<number | null>(null)

  const options = useMemo(() => {
    const all = ratingOptions(prefer)
    const query = value.trim().toLowerCase()
    if (!query) {
      return all
    }
    // Exact and prefix matches first, then anything containing the text.
    return all
      .filter(option => (
        option.value.toLowerCase().includes(query)
        || option.meaning.toLowerCase().includes(query)
      ))
      .sort((a, b) => {
        const rank = (option: RatingOption) => (
          option.value.toLowerCase() === query
            ? 0
            : option.value.toLowerCase().startsWith(query)
              ? 1
              : 2
        )
        return rank(a) - rank(b)
      })
  }, [prefer, value])

  function choose(option: RatingOption) {
    onChange(option.value)
    setOpen(false)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault()
      setOpen(true)
      setActive(current => Math.min(current + 1, Math.max(options.length - 1, 0)))
    } else if (event.key === "ArrowUp") {
      event.preventDefault()
      setActive(current => Math.max(current - 1, 0))
    } else if (event.key === "Enter" && open && options[active]) {
      event.preventDefault()
      choose(options[active])
    } else if (event.key === "Escape" && open) {
      event.preventDefault()
      setOpen(false)
    }
  }

  const showList = open && !disabled && options.length > 0

  return (
    <div className="relative">
      <Input
        id={inputId}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && options[active] ? `${listId}-${active}` : undefined}
        autoComplete="off"
        maxLength={64}
        placeholder="Type or pick a rating"
        value={value}
        disabled={disabled}
        onChange={event => {
          onChange(event.target.value)
          setActive(0)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
        onBlur={() => {
          // Let a click on an option land before the list closes.
          blurTimer.current = window.setTimeout(() => setOpen(false), 120)
        }}
        onKeyDown={handleKeyDown}
      />

      {showList && (
        <ul
          id={listId}
          role="listbox"
          className="
            absolute z-50 mt-1 max-h-64 w-full overflow-y-auto rounded-md border
            bg-popover p-1 text-sm text-popover-foreground shadow-md
          "
          onMouseDown={event => {
            // Keep focus in the input while picking.
            event.preventDefault()
            if (blurTimer.current) {
              window.clearTimeout(blurTimer.current)
            }
          }}
        >
          {options.map((option, index) => {
            const startsGroup = index === 0 || options[index - 1].group !== option.group
            return (
              <li key={option.value} role="presentation">
                {startsGroup && !value.trim() && (
                  <div className="px-2 pt-1 text-[0.65rem] uppercase tracking-wide text-muted-foreground">
                    {option.group}
                  </div>
                )}
                <div
                  id={`${listId}-${index}`}
                  role="option"
                  aria-selected={index === active}
                  className={[
                    "flex cursor-pointer items-baseline gap-2 rounded px-2 py-1",
                    index === active ? "bg-accent text-accent-foreground" : "",
                  ].join(" ")}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => choose(option)}
                >
                  <span className="w-20 shrink-0 font-medium">{option.value}</span>
                  <span className="text-muted-foreground">{option.meaning}</span>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
