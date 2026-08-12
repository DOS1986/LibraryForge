import {
  useEffect,
  useState,
  type FormEvent,
} from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type {
  OnlineVideoSemanticCandidate,
  SemanticResolveInput,
} from "@/types"


export function OnlineVideoManualMatchForm({
  seed,
  busy = false,
  onSubmit,
}: {
  seed: OnlineVideoSemanticCandidate | null
  busy?: boolean
  onSubmit: (input: SemanticResolveInput) => Promise<void>
}) {
  const [provider, setProvider] = useState("youtube")
  const [videoId, setVideoId] = useState("")
  const [title, setTitle] = useState("")
  const [channelId, setChannelId] = useState("")
  const [channelTitle, setChannelTitle] = useState("")
  const [channelHandle, setChannelHandle] = useState("")
  const [sourceUrl, setSourceUrl] = useState("")
  const [uploadDate, setUploadDate] = useState("")
  const [videoKind, setVideoKind] = useState("unknown")
  const [lock, setLock] = useState(true)
  const [notes, setNotes] = useState("")

  useEffect(() => {
    setProvider(seed?.provider || "youtube")
    setVideoId(seed?.source_id || "")
    setTitle(seed?.title || "")
    setChannelId(seed?.channel_id || "")
    setChannelTitle(seed?.channel_title || "")
    setChannelHandle(seed?.channel_handle || "")
    setSourceUrl(seed?.source_url || "")
    setUploadDate(seed?.upload_date || "")
    setVideoKind(seed?.video_kind || "unknown")
    setLock(true)
    setNotes("")
  }, [seed])

  async function submit(event: FormEvent) {
    event.preventDefault()

    await onSubmit({
      candidate_source: "manual",
      kind: "online_video",
      lock,
      notes,
      provider: provider.trim(),
      video_id: videoId.trim(),
      title: title.trim(),
      channel_id: channelId.trim(),
      channel_title: channelTitle.trim(),
      channel_handle: channelHandle.trim(),
      source_url: sourceUrl.trim(),
      upload_date: uploadDate || null,
      video_kind: videoKind,
    })
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="online-provider">Provider</Label>
          <Input
            id="online-provider"
            value={provider}
            onChange={event => setProvider(event.target.value)}
            placeholder="youtube"
            required
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="online-video-id">Video / Source ID</Label>
          <Input
            id="online-video-id"
            value={videoId}
            onChange={event => setVideoId(event.target.value)}
            placeholder="UK4X75tY6_k"
            required
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="online-title">Title</Label>
        <Input
          id="online-title"
          value={title}
          onChange={event => setTitle(event.target.value)}
          placeholder="Optional canonical title"
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="online-channel-id">Channel ID</Label>
          <Input
            id="online-channel-id"
            value={channelId}
            onChange={event => setChannelId(event.target.value)}
            placeholder="UC..."
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="online-channel-title">Channel Name</Label>
          <Input
            id="online-channel-title"
            value={channelTitle}
            onChange={event => setChannelTitle(event.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="online-channel-handle">Channel Handle</Label>
          <Input
            id="online-channel-handle"
            value={channelHandle}
            onChange={event => setChannelHandle(event.target.value)}
            placeholder="@channel"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="online-kind">Video Type</Label>
          <select
            id="online-kind"
            value={videoKind}
            onChange={event => setVideoKind(event.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
          >
            <option value="unknown">Unknown</option>
            <option value="video">Video</option>
            <option value="short">Short</option>
            <option value="stream">Stream</option>
          </select>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="online-upload-date">Upload Date</Label>
          <Input
            id="online-upload-date"
            type="date"
            value={uploadDate}
            onChange={event => setUploadDate(event.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="online-source-url">Source URL</Label>
          <Input
            id="online-source-url"
            value={sourceUrl}
            onChange={event => setSourceUrl(event.target.value)}
          />
        </div>
      </div>

      <label className="flex items-start gap-3 rounded-md border p-3 text-sm">
        <input
          type="checkbox"
          checked={lock}
          onChange={event => setLock(event.target.checked)}
          className="mt-0.5"
        />
        <span>
          <span className="block font-medium">Lock this identity</span>
          <span className="text-muted-foreground">
            Future semantic rebuilds will preserve this provider/video assignment until it is unlocked or reset.
          </span>
        </span>
      </label>

      <div className="space-y-2">
        <Label htmlFor="online-notes">Notes</Label>
        <textarea
          id="online-notes"
          value={notes}
          onChange={event => setNotes(event.target.value)}
          placeholder="Why this identity was chosen..."
          rows={4}
          className="flex min-h-24 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
      </div>

      <Button type="submit" disabled={busy || !provider.trim() || !videoId.trim()}>
        {busy ? "Saving..." : "Save Online Video Match"}
      </Button>
    </form>
  )
}
