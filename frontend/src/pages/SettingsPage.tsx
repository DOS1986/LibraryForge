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
  Input,
} from "@/components/ui/input"

import {
  useUserSettings,
} from "@/lib/user-settings"

import type {
  NeedsAttentionOrdering,
  PageSize,
  UserSettingsUpdate,
} from "@/types"


const attentionSortOptions: Array<{
  value: NeedsAttentionOrdering
  label: string
}> = [
  {
    value: "confidence",
    label: "Confidence — lowest first",
  },
  {
    value: "-confidence",
    label: "Confidence — highest first",
  },
  {
    value: "-updated_at",
    label: "Recently updated first",
  },
  {
    value: "updated_at",
    label: "Oldest updated first",
  },
  {
    value: "media_file__file_name",
    label: "File name — A to Z",
  },
  {
    value: "-media_file__file_name",
    label: "File name — Z to A",
  },
  {
    value: "media_file__relative_path",
    label: "Path — A to Z",
  },
  {
    value: "-media_file__relative_path",
    label: "Path — Z to A",
  },
  {
    value: "source",
    label: "Source — A to Z",
  },
  {
    value: "-source",
    label: "Source — Z to A",
  },
]


export function SettingsPage() {
  const {
    settings,
    loading,
    error,
    save,
  } = useUserSettings()

  const [form, setForm] =
    useState<UserSettingsUpdate>({})

  const [saving, setSaving] =
    useState(false)

  const [saved, setSaved] =
    useState(false)

  const [saveError, setSaveError] =
    useState<string | null>(null)


  useEffect(
    () => {
      if (!settings) {
        return
      }

      setForm({
        display_name: settings.display_name,
        default_page_size: settings.default_page_size,
        needs_attention_unresolved_sort:
          settings.needs_attention_unresolved_sort,
        needs_attention_conflict_sort:
          settings.needs_attention_conflict_sort,
        needs_attention_confirmed_sort:
          settings.needs_attention_confirmed_sort,
        show_build_information:
          settings.show_build_information,
        confirm_restart:
          settings.confirm_restart,
      })
    },
    [settings],
  )


  async function handleSave() {
    setSaving(true)
    setSaved(false)
    setSaveError(null)

    try {
      await save(form)
      setSaved(true)
    } catch (err) {
      setSaveError(
        err instanceof Error
          ? err.message
          : "Unable to save settings.",
      )
    } finally {
      setSaving(false)
    }
  }


  if (loading && !settings) {
    return (
      <div className="text-sm text-muted-foreground">
        Loading settings...
      </div>
    )
  }


  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
          <CardDescription>
            These preferences are stored with your LibraryForge user account and follow you between browsers.
          </CardDescription>
        </CardHeader>
      </Card>

      {(error || saveError) && (
        <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
          {saveError || error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>
            Control how your account is displayed in LibraryForge.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-5">
          <div className="space-y-2">
            <label className="text-sm font-medium">
              Display name
            </label>
            <Input
              value={form.display_name ?? ""}
              onChange={(event) => {
                setSaved(false)
                setForm((value) => ({
                  ...value,
                  display_name: event.target.value,
                }))
              }}
              placeholder="Your name"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">
              Email
            </label>
            <Input
              value={settings?.email ?? ""}
              disabled
            />
            <div className="text-xs text-muted-foreground">
              Authentication email is managed by your user account, not this preferences page.
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Interface</CardTitle>
          <CardDescription>
            Defaults used across LibraryForge tables and development information.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-5">
          <div className="space-y-2">
            <label className="text-sm font-medium">
              Default page size
            </label>
            <select
              className="h-10 w-full rounded-md border bg-background px-3 text-sm"
              value={form.default_page_size ?? 20}
              onChange={(event) => {
                setSaved(false)
                setForm((value) => ({
                  ...value,
                  default_page_size: Number(
                    event.target.value,
                  ) as PageSize,
                }))
              }}
            >
              {[10, 20, 50, 100].map((size) => (
                <option key={size} value={size}>
                  {size} rows
                </option>
              ))}
            </select>
          </div>

          <label className="flex items-center justify-between gap-4 rounded-md border p-4">
            <div>
              <div className="font-medium">
                Show build information
              </div>
              <div className="text-sm text-muted-foreground">
                Keep the frontend/backend build card visible in the main navigation.
              </div>
            </div>
            <input
              type="checkbox"
              checked={form.show_build_information ?? true}
              onChange={(event) => {
                setSaved(false)
                setForm((value) => ({
                  ...value,
                  show_build_information: event.target.checked,
                }))
              }}
              className="h-4 w-4"
            />
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Needs Attention</CardTitle>
          <CardDescription>
            Choose the default server-side sort used when each review queue opens. You can still click table headers to sort differently while reviewing.
          </CardDescription>
        </CardHeader>

        <CardContent className="grid gap-5 xl:grid-cols-3">
          {([
            [
              "Unresolved",
              "needs_attention_unresolved_sort",
            ],
            [
              "Conflicts",
              "needs_attention_conflict_sort",
            ],
            [
              "Confirmed",
              "needs_attention_confirmed_sort",
            ],
          ] as const).map(([label, field]) => (
            <div key={field} className="space-y-2">
              <label className="text-sm font-medium">
                {label}
              </label>
              <select
                className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                value={form[field] ?? "-updated_at"}
                onChange={(event) => {
                  setSaved(false)
                  setForm((value) => ({
                    ...value,
                    [field]: event.target.value as NeedsAttentionOrdering,
                  }))
                }}
              >
                {attentionSortOptions.map((option) => (
                  <option
                    key={option.value}
                    value={option.value}
                  >
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>System Actions</CardTitle>
          <CardDescription>
            Safety preferences for administrator-only application controls.
          </CardDescription>
        </CardHeader>

        <CardContent>
          <label className="flex items-center justify-between gap-4 rounded-md border p-4">
            <div>
              <div className="font-medium">
                Confirm before restarting
              </div>
              <div className="text-sm text-muted-foreground">
                Show a confirmation dialog before requesting a LibraryForge restart.
              </div>
            </div>
            <input
              type="checkbox"
              checked={form.confirm_restart ?? true}
              onChange={(event) => {
                setSaved(false)
                setForm((value) => ({
                  ...value,
                  confirm_restart: event.target.checked,
                }))
              }}
              className="h-4 w-4"
            />
          </label>
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-3">
        {saved && (
          <span className="text-sm text-muted-foreground">
            Settings saved.
          </span>
        )}

        <Button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving}
        >
          {saving ? "Saving..." : "Save Settings"}
        </Button>
      </div>
    </div>
  )
}
