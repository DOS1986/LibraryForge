import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react"

import { CornerDownLeft, Moon, Plus, Rows4, Search, Sun, type LucideIcon } from "lucide-react"
import { useNavigate } from "react-router-dom"

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"

import { LIBRARY_SECTIONS, MAIN_NAV, SETUP_NAV, libraryIcon } from "@/lib/navigation"
import { useTheme } from "@/lib/theme-context"
import { cn } from "@/lib/utils"

import type { Library } from "@/types"


interface Command {
  id: string
  label: string
  group: string
  hint?: string
  icon: LucideIcon
  keywords: string
  run: () => void
}


// 0 when a word is missing; otherwise higher when words start words in the title.
function score(command: Command, words: string[]) {
  const label = command.label.toLowerCase()
  const labelWords = label.split(/[^a-z0-9]+/)
  const rest = `${command.group} ${command.hint ?? ""} ${command.keywords}`.toLowerCase()
  let total = 0
  for (const word of words) {
    if (labelWords.some(part => part.startsWith(word))) {
      total += 4
    } else if (label.includes(word)) {
      total += 2
    } else if (rest.includes(word)) {
      total += 1
    } else {
      return 0
    }
  }
  return total
}


/** Ctrl/Cmd+K: jump to any page, library page, or appearance setting by typing. */
export function CommandPalette({
  open,
  onOpenChange,
  libraries,
  onAddLibrary,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  libraries: Library[]
  onAddLibrary: () => void
}) {
  const navigate = useNavigate()
  const { resolved, density, setMode, setDensity } = useTheme()
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const listRef = useRef<HTMLUListElement>(null)

  const commands = useMemo<Command[]>(() => {
    const go = (path: string) => () => navigate(path)
    const output: Command[] = [...MAIN_NAV, ...SETUP_NAV].map(item => ({
      id: item.path,
      label: item.label,
      group: "Go to",
      hint: item.description,
      icon: item.icon,
      keywords: item.keywords ?? "",
      run: go(item.path),
    }))
    for (const library of libraries) {
      const Icon = libraryIcon(library)
      for (const section of LIBRARY_SECTIONS) {
        output.push({
          id: `${library.id}/${section.path}`,
          label: section.path === "overview" ? library.name : `${library.name} › ${section.label}`,
          group: "Libraries",
          hint: section.path === "overview" ? library.content_type_label : section.description,
          icon: section.path === "overview" ? Icon : section.icon,
          keywords: `${library.name} ${section.label} ${section.keywords ?? ""}`,
          run: go(`/libraries/${library.id}/${section.path}`),
        })
      }
    }
    output.push(
      {
        id: "add-library",
        label: "Add a library",
        group: "Actions",
        icon: Plus,
        keywords: "new create folder",
        run: onAddLibrary,
      },
      {
        id: "theme",
        label: resolved === "dark" ? "Switch to light mode" : "Switch to dark mode",
        group: "Appearance",
        icon: resolved === "dark" ? Sun : Moon,
        keywords: "theme dark light mode appearance",
        run: () => setMode(resolved === "dark" ? "light" : "dark"),
      },
      {
        id: "density",
        label: density === "compact" ? "Use comfortable spacing" : "Use compact spacing",
        group: "Appearance",
        icon: Rows4,
        keywords: "density compact comfortable spacing tables",
        run: () => setDensity(density === "compact" ? "comfortable" : "compact"),
      },
    )
    return output
  }, [libraries, navigate, onAddLibrary, resolved, density, setMode, setDensity])

  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  // With no query, show pages and each library's overview, not every library page.
  const results = words.length
    ? commands
      .map(command => ({ command, rank: score(command, words) }))
      .filter(item => item.rank > 0)
      .sort((a, b) => b.rank - a.rank)
      .slice(0, 50)
      .map(item => item.command)
    : commands.filter(command => command.group !== "Libraries" || !command.label.includes("›"))

  useEffect(() => {
    setActive(0)
  }, [query, open])

  useEffect(() => {
    if (!open) {
      setQuery("")
    }
  }, [open])

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" })
  }, [active])

  function run(command: Command | undefined) {
    if (!command) {
      return
    }
    onOpenChange(false)
    command.run()
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault()
      setActive(index => Math.min(index + 1, results.length - 1))
    } else if (event.key === "ArrowUp") {
      event.preventDefault()
      setActive(index => Math.max(index - 1, 0))
    } else if (event.key === "Enter") {
      event.preventDefault()
      run(results[active])
    }
  }

  let lastGroup = ""

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false} className="top-[15%] translate-y-0 gap-0 overflow-hidden p-0 sm:max-w-xl">
        <DialogTitle className="sr-only">Quick search</DialogTitle>
        <DialogDescription className="sr-only">Type to find a page, library, or setting, then press Enter.</DialogDescription>
        <div className="flex items-center gap-2 border-b px-4">
          <Search className="size-4 text-muted-foreground" />
          <input
            autoFocus
            value={query}
            onChange={event => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search pages, libraries, and settings..."
            aria-label="Search"
            aria-controls="command-results"
            aria-activedescendant={results[active] ? `command-${results[active].id}` : undefined}
            className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <kbd className="rounded border bg-muted px-1.5 py-0.5 text-[0.6875rem] text-muted-foreground">Esc</kbd>
        </div>
        <ul id="command-results" ref={listRef} role="listbox" className="max-h-[min(60vh,26rem)] overflow-y-auto p-2">
          {results.length === 0 && (
            <li className="px-3 py-8 text-center text-sm text-muted-foreground">Nothing matches &quot;{query}&quot;.</li>
          )}
          {results.map((command, index) => {
            // Results are ranked when searching, so group headings only show for the default list.
            const heading = !words.length && command.group !== lastGroup ? command.group : null
            lastGroup = command.group
            return (
              <li key={command.id} role="presentation">
                {heading && <div className="px-3 pt-2 pb-1 text-xs font-medium text-muted-foreground">{heading}</div>}
                <div
                  id={`command-${command.id}`}
                  role="option"
                  aria-selected={index === active}
                  data-index={index}
                  onMouseMove={() => setActive(index)}
                  onClick={() => run(command)}
                  className={cn(
                    "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm",
                    index === active ? "bg-accent text-accent-foreground" : "text-foreground",
                  )}
                >
                  <command.icon className="size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate">{command.label}</span>
                  {command.hint && <span className="hidden truncate text-xs text-muted-foreground sm:inline">{command.hint}</span>}
                  {index === active && <CornerDownLeft className="size-3.5 text-muted-foreground" />}
                </div>
              </li>
            )
          })}
        </ul>
      </DialogContent>
    </Dialog>
  )
}
