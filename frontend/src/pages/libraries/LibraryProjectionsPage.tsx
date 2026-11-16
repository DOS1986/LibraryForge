import { useCallback, useEffect, useState, type FormEvent } from "react"

import { ProjectionPanel } from "@/components/projections/ProjectionPanel"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

import { createOutputProfile, getOutputProfiles } from "@/lib/api"
import { useLibraryOutlet } from "@/lib/route-context"

import type { OutputProfile } from "@/types"


type OutputTarget = OutputProfile["target"]

const TARGETS: { value: OutputTarget; label: string }[] = [
  { value: "jellyfin", label: "Jellyfin" },
  { value: "emby", label: "Emby" },
  { value: "kodi", label: "Kodi" },
  { value: "generic", label: "Generic" },
]

const SELECT_CLASS = "h-9 w-full rounded-lg border bg-card px-2 text-sm shadow-xs"


export function LibraryProjectionsPage() {
  const { library } = useLibraryOutlet()
  const [profiles, setProfiles] = useState<OutputProfile[]>([])
  const [name, setName] = useState("")
  const [target, setTarget] = useState<OutputTarget>("jellyfin")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setProfiles(await getOutputProfiles())
  }, [])

  useEffect(() => {
    void load().catch(err => setError(err instanceof Error ? err.message : "Unable to load output profiles."))
  }, [load])

  async function addProfile(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await createOutputProfile({ name: name.trim(), target, nfo_root_element: "movie" })
      setName("")
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create the output profile.")
    } finally {
      setSaving(false)
    }
  }

  const projectable = ["movies", "tv", "online_video", "mixed"].includes(library.content_type)

  return (
    <div className="space-y-6">
      {projectable ? (
        <ProjectionPanel libraryId={library.id} libraryPath={library.path} contentType={library.content_type} />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Projections</CardTitle>
            <CardDescription>
              Projections are available for movie, TV, online video, and mixed libraries. Set this library&apos;s content
              type in its Settings to project it.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Output profiles</CardTitle>
          <CardDescription>The media server each projection writes for: its naming, NFO, and artwork conventions.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          {profiles.length > 0 ? (
            <ul className="divide-y rounded-lg border">
              {profiles.map(profile => (
                <li key={profile.id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <span className="font-medium">{profile.name}</span>
                  <Badge variant="secondary">{profile.target_label}</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">No output profiles yet. Setting up a Jellyfin folder creates one for you.</p>
          )}

          <form className="grid gap-3 sm:grid-cols-[1fr_12rem_auto] sm:items-end" onSubmit={addProfile}>
            <div className="space-y-1.5">
              <Label htmlFor="profile-name">New profile name</Label>
              <Input id="profile-name" value={name} maxLength={255} onChange={event => setName(event.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="profile-target">Media server</Label>
              <select id="profile-target" className={SELECT_CLASS} value={target} onChange={event => setTarget(event.target.value as OutputTarget)}>
                {TARGETS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </div>
            <Button type="submit" disabled={saving || !name.trim()}>{saving ? "Adding..." : "Add profile"}</Button>
          </form>
          {error && <p className="text-destructive" role="alert">{error}</p>}
        </CardContent>
      </Card>
    </div>
  )
}
