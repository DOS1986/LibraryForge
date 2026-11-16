import { useEffect, useState, type FormEvent } from "react"

import { Lock } from "lucide-react"

import { RatingCombobox } from "@/components/ratings/RatingCombobox"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

import { getChannelEditor, getOnlineVideoEditor, updateChannelEditor, updateOnlineVideoEditor } from "@/lib/api"
import { formatDateTime } from "@/lib/format"

import type { ChannelEditorDetail, EditorFieldState, EditorHistoryEntry, OnlineVideoEditorDetail } from "@/types"


export type OnlineEditorTarget = { kind: "online_video" | "channel"; id: string } | null

type Detail = OnlineVideoEditorDetail | ChannelEditorDetail

interface FormState {
  title: string
  sort_title: string
  description: string
  content_rating: string
  upload_date: string
  tags: string
  note: string
}

const TEXTAREA = "min-h-32 w-full rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/25 dark:bg-input/20"

const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  sort_title: "Sort title",
  description: "Description",
  content_rating: "Rating",
  upload_date: "Upload date",
  release_date: "Release date",
  tags: "Tags",
}


function formFrom(detail: Detail): FormState {
  return {
    title: detail.title,
    sort_title: detail.kind === "channel" ? detail.sort_title : "",
    description: detail.description,
    content_rating: detail.content_rating,
    upload_date: detail.kind === "online_video" ? detail.upload_date ?? "" : "",
    tags: detail.kind === "online_video" ? detail.tags.join(", ") : "",
    note: "",
  }
}


function changes(detail: Detail, form: FormState): Record<string, unknown> {
  const values: Record<string, unknown> = {}
  if (form.title.trim() !== detail.title) values.title = form.title
  if (form.description !== detail.description) values.description = form.description
  if (form.content_rating.trim() !== detail.content_rating) values.content_rating = form.content_rating
  if (detail.kind === "channel" && form.sort_title.trim() !== detail.sort_title) values.sort_title = form.sort_title
  if (detail.kind === "online_video") {
    if ((form.upload_date || null) !== detail.upload_date) values.upload_date = form.upload_date || null
    const tags = form.tags.split(",").map(tag => tag.trim()).filter(Boolean)
    if (tags.join("\u0000") !== detail.tags.join("\u0000")) values.tags = tags
  }
  return values
}


function SourceNote({ states, field }: { states: EditorFieldState[]; field: string }) {
  const state = states.find(item => item.field_name === field)
  if (!state) {
    return null
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      {state.locked && <Lock className="size-3" aria-label="Locked" />}
      {state.source_label}
    </span>
  )
}


function History({ entries }: { entries: EditorHistoryEntry[] }) {
  if (!entries.length) {
    return <p className="text-sm text-muted-foreground">No changes recorded yet.</p>
  }
  return (
    <ul className="space-y-2 text-sm">
      {entries.map(entry => (
        <li key={entry.id} className="rounded-lg border p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{entry.source_label}</Badge>
            <span className="text-xs text-muted-foreground">{formatDateTime(entry.created_at)}</span>
          </div>
          <ul className="mt-2 space-y-1">
            {Object.entries(entry.changes).map(([field, change]) => (
              <li key={field} className="break-words">
                <span className="font-medium">{FIELD_LABELS[field] ?? field}:</span>{" "}
                <span className="text-muted-foreground line-through">{String(change.old ?? "—").slice(0, 120)}</span>{" "}
                → {String(change.new ?? "—").slice(0, 120)}
              </li>
            ))}
          </ul>
          {entry.note && <p className="mt-1 text-xs text-muted-foreground">{entry.note}</p>}
        </li>
      ))}
    </ul>
  )
}


/** Edit an online video's or channel's metadata. Saved fields are locked against later scans. */
export function OnlineVideoEditorDialog({
  target,
  onClose,
  onSaved,
}: {
  target: OnlineEditorTarget
  onClose: () => void
  onSaved?: () => void
}) {
  const [detail, setDetail] = useState<Detail | null>(null)
  const [form, setForm] = useState<FormState | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setDetail(null)
    setForm(null)
    setMessage(null)
    setError(null)
    if (!target) {
      return
    }
    const load = target.kind === "channel" ? getChannelEditor(target.id) : getOnlineVideoEditor(target.id)
    load
      .then(result => {
        setDetail(result)
        setForm(formFrom(result))
      })
      .catch(err => setError(err instanceof Error ? err.message : "Unable to load this item."))
  }, [target])

  const pending = detail && form ? changes(detail, form) : {}
  const dirty = Object.keys(pending).length > 0

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!detail || !form || !dirty) {
      return
    }
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const values = { ...pending, ...(form.note.trim() ? { note: form.note.trim() } : {}) }
      const result = detail.kind === "channel"
        ? await updateChannelEditor(detail.id, values)
        : await updateOnlineVideoEditor(detail.id, values)
      setDetail(result)
      setForm(formFrom(result))
      setMessage("Saved. These fields are now locked, so scans won't overwrite them. The Jellyfin Shows folder picks them up on its next sync.")
      onSaved?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save.")
    } finally {
      setSaving(false)
    }
  }

  const set = (field: keyof FormState) => (value: string) => setForm(current => (current ? { ...current, [field]: value } : current))
  const states = detail?.field_states ?? []

  return (
    <Dialog open={target !== null} onOpenChange={open => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{detail ? `Edit ${detail.kind === "channel" ? "channel" : "video"}` : "Loading..."}</DialogTitle>
          <DialogDescription>
            {detail?.kind === "online_video" && detail.channel ? `${detail.channel.title} · ` : ""}
            {detail ? `${detail.provider} ${detail.source_id}` : ""}
          </DialogDescription>
        </DialogHeader>

        {error && <p className="text-sm text-destructive" role="alert">{error}</p>}

        {detail && form && (
          <Tabs defaultValue="metadata">
            <TabsList>
              <TabsTrigger value="metadata">Metadata</TabsTrigger>
              <TabsTrigger value="history">History ({detail.history.length})</TabsTrigger>
            </TabsList>

            <TabsContent value="metadata" className="mt-4">
              <form className="space-y-4" onSubmit={save}>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <Label htmlFor="ov-title">Title</Label>
                    <SourceNote states={states} field="title" />
                  </div>
                  <Input id="ov-title" value={form.title} maxLength={1024} onChange={event => set("title")(event.target.value)} />
                </div>

                {detail.kind === "channel" && (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <Label htmlFor="ov-sort">Sort title</Label>
                      <SourceNote states={states} field="sort_title" />
                    </div>
                    <Input id="ov-sort" value={form.sort_title} onChange={event => set("sort_title")(event.target.value)} />
                  </div>
                )}

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <Label htmlFor="ov-rating">Rating</Label>
                      <SourceNote states={states} field="content_rating" />
                    </div>
                    <RatingCombobox id="ov-rating" value={form.content_rating} onChange={set("content_rating")} prefer="tv" />
                  </div>
                  {detail.kind === "online_video" && (
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between gap-2">
                        <Label htmlFor="ov-date">Upload date</Label>
                        <SourceNote states={states} field="upload_date" />
                      </div>
                      <Input id="ov-date" type="date" value={form.upload_date} onChange={event => set("upload_date")(event.target.value)} />
                    </div>
                  )}
                </div>

                {detail.kind === "online_video" && detail.channel && !form.content_rating && detail.channel.content_rating && (
                  <p className="text-xs text-muted-foreground">
                    With no rating of its own, this video uses its channel&apos;s rating ({detail.channel.content_rating}).
                  </p>
                )}

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <Label htmlFor="ov-description">Description</Label>
                    <SourceNote states={states} field="description" />
                  </div>
                  <textarea id="ov-description" className={TEXTAREA} value={form.description} onChange={event => set("description")(event.target.value)} />
                </div>

                {detail.kind === "online_video" && (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <Label htmlFor="ov-tags">Tags</Label>
                      <SourceNote states={states} field="tags" />
                    </div>
                    <Input id="ov-tags" value={form.tags} placeholder="Comma-separated" onChange={event => set("tags")(event.target.value)} />
                  </div>
                )}

                <div className="space-y-1.5">
                  <Label htmlFor="ov-note">Note for history (optional)</Label>
                  <Input id="ov-note" value={form.note} maxLength={500} onChange={event => set("note")(event.target.value)} />
                </div>

                {message && <p className="text-sm text-success" role="status">{message}</p>}

                <div className="flex flex-wrap items-center gap-2">
                  <Button type="submit" disabled={!dirty || saving}>
                    {saving ? "Saving..." : dirty ? `Save ${Object.keys(pending).length} change${Object.keys(pending).length === 1 ? "" : "s"}` : "No changes"}
                  </Button>
                  <Button type="button" variant="outline" disabled={!dirty || saving} onClick={() => setForm(formFrom(detail))}>
                    Undo changes
                  </Button>
                </div>
              </form>
            </TabsContent>

            <TabsContent value="history" className="mt-4">
              <History entries={detail.history} />
            </TabsContent>
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  )
}
