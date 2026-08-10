import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

import {
  getUserSettings,
  updateUserSettings,
} from "@/lib/api"

import type {
  UserSettings,
  UserSettingsUpdate,
} from "@/types"


interface UserSettingsContextValue {
  settings: UserSettings | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  save: (
    input: UserSettingsUpdate,
  ) => Promise<UserSettings>
}


const UserSettingsContext =
  createContext<UserSettingsContextValue | null>(
    null,
  )


export function UserSettingsProvider({
  children,
}: {
  children: ReactNode
}) {
  const [settings, setSettings] =
    useState<UserSettings | null>(null)

  const [loading, setLoading] =
    useState(true)

  const [error, setError] =
    useState<string | null>(null)


  const refresh = useCallback(
    async () => {
      setLoading(true)
      setError(null)

      try {
        setSettings(
          await getUserSettings(),
        )
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load user settings.",
        )
      } finally {
        setLoading(false)
      }
    },
    [],
  )


  useEffect(
    () => {
      void refresh()
    },
    [refresh],
  )


  const save = useCallback(
    async (
      input: UserSettingsUpdate,
    ) => {
      const updated =
        await updateUserSettings(input)

      setSettings(updated)
      return updated
    },
    [],
  )


  const value = useMemo(
    () => ({
      settings,
      loading,
      error,
      refresh,
      save,
    }),
    [
      settings,
      loading,
      error,
      refresh,
      save,
    ],
  )


  return (
    <UserSettingsContext.Provider
      value={value}
    >
      {children}
    </UserSettingsContext.Provider>
  )
}


export function useUserSettings() {
  const context =
    useContext(UserSettingsContext)

  if (!context) {
    throw new Error(
      "useUserSettings must be used inside UserSettingsProvider.",
    )
  }

  return context
}
