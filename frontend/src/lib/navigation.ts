import {
  Activity,
  Clapperboard,
  FileCode2,
  Film,
  FolderOutput,
  FolderSymlink,
  FolderTree,
  Layers,
  LayoutDashboard,
  LibraryBig,
  ListChecks,
  MonitorPlay,
  Plug,
  Server,
  Settings,
  Settings2,
  ShieldCheck,
  TriangleAlert,
  Tv,
  type LucideIcon,
} from "lucide-react"

import type { Library, LibraryContentType } from "@/types"


export interface NavItem {
  path: string
  label: string
  icon: LucideIcon
  description: string
  keywords?: string
}


// Top-level pages, in sidebar order. Libraries sit between the two groups.
export const MAIN_NAV: NavItem[] = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard, description: "Libraries at a glance" },
  {
    path: "/outputs",
    label: "Outputs",
    icon: FolderOutput,
    description: "Projection folders and NFO output, their plans and run history",
    keywords: "projections jellyfin emby kodi nfo artwork cleanup runs",
  },
  { path: "/jobs", label: "Jobs", icon: ListChecks, description: "Library scans and their progress", keywords: "scan worker queue" },
]

export const SETUP_NAV: NavItem[] = [
  {
    path: "/settings/integrations",
    label: "Integrations",
    icon: Plug,
    description: "TMDB, OMDb, TheTVDB, Fanart.tv, YouTube, TubeArchivist, Jellyfin",
    keywords: "connections providers api keys",
  },
  { path: "/settings", label: "Settings", icon: Settings, description: "Your account and preferences", keywords: "profile preferences" },
  { path: "/system", label: "System", icon: Server, description: "Health, version, and credits", keywords: "status health version credits" },
]


// A library's pages, in sidebar order.
export const LIBRARY_SECTIONS: NavItem[] = [
  { path: "overview", label: "Overview", icon: LayoutDashboard, description: "Summary and scan status" },
  { path: "media", label: "Media", icon: Clapperboard, description: "Browse and edit titles", keywords: "catalog movies series videos" },
  { path: "files", label: "Files", icon: FolderTree, description: "Files on disk" },
  { path: "nfo", label: "NFO", icon: FileCode2, description: "Indexed NFO files", keywords: "xml sidecar" },
  { path: "sources", label: "Sources", icon: Layers, description: "Metadata found in files and sidecars", keywords: "embedded tubearchivist yt-dlp ffprobe filename" },
  { path: "attention", label: "Needs Attention", icon: TriangleAlert, description: "Items to review", keywords: "matches problems" },
  { path: "ratings", label: "Ratings", icon: ShieldCheck, description: "Content ratings for parental controls", keywords: "mpaa pg parental" },
  { path: "projections", label: "Projections", icon: FolderSymlink, description: "Media server folders built from this library", keywords: "youtube shows hardlinks output jellyfin emby kodi" },
  { path: "settings", label: "Settings", icon: Settings2, description: "Management mode and library options" },
]


const CONTENT_ICONS: Partial<Record<LibraryContentType, LucideIcon>> = {
  movies: Film,
  tv: Tv,
  online_video: MonitorPlay,
}


export function libraryIcon(library: Pick<Library, "content_type">): LucideIcon {
  return CONTENT_ICONS[library.content_type] ?? LibraryBig
}


export function librarySection(path: string): NavItem | undefined {
  return LIBRARY_SECTIONS.find(section => section.path === path)
}


export const JOBS_ICON = Activity
