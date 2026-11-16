import { createContext, useContext } from "react"


export type ThemeMode = "light" | "dark" | "system"
export type Density = "comfortable" | "compact"

export interface ThemeContextValue {
  mode: ThemeMode
  resolved: "light" | "dark"
  density: Density
  setMode: (mode: ThemeMode) => void
  setDensity: (density: Density) => void
  toggle: () => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)


export function useTheme() {
  const value = useContext(ThemeContext)
  if (!value) {
    throw new Error("useTheme must be used inside ThemeProvider.")
  }
  return value
}
