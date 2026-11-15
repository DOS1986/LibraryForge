import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

import { ThemeContext, type Density, type ThemeContextValue, type ThemeMode } from "@/lib/theme-context"

// Keep these keys in sync with the early script in index.html, which applies
// the saved theme before React loads so pages never flash the wrong colors.
const THEME_KEY = "libraryforge.theme"
const DENSITY_KEY = "libraryforge.density"

function read<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = window.localStorage.getItem(key)
    return value && (allowed as readonly string[]).includes(value) ? (value as T) : fallback
  } catch {
    return fallback
  }
}


function write(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Storage can be unavailable (private browsing); the choice lasts this visit.
  }
}


function systemPrefersDark() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches
}


export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(() => read(THEME_KEY, ["light", "dark", "system"], "system"))
  const [density, setDensityState] = useState<Density>(() => read(DENSITY_KEY, ["comfortable", "compact"], "comfortable"))
  const [systemDark, setSystemDark] = useState(systemPrefersDark)

  useEffect(() => {
    const query = window.matchMedia?.("(prefers-color-scheme: dark)")
    if (!query) {
      return
    }
    const listener = (event: MediaQueryListEvent) => setSystemDark(event.matches)
    query.addEventListener("change", listener)
    return () => query.removeEventListener("change", listener)
  }, [])

  const resolved = mode === "system" ? (systemDark ? "dark" : "light") : mode

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", resolved === "dark")
    root.style.colorScheme = resolved
  }, [resolved])

  useEffect(() => {
    document.documentElement.dataset.density = density
  }, [density])

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next)
    write(THEME_KEY, next)
  }, [])

  const setDensity = useCallback((next: Density) => {
    setDensityState(next)
    write(DENSITY_KEY, next)
  }, [])

  const value = useMemo<ThemeContextValue>(() => ({
    mode,
    resolved,
    density,
    setMode,
    setDensity,
    toggle: () => setMode(resolved === "dark" ? "light" : "dark"),
  }), [mode, resolved, density, setMode, setDensity])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

