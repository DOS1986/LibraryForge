import { useId } from "react"

import { cn } from "@/lib/utils"


/**
 * The LibraryForge mark: three book spines on a forge anvil base, with a
 * spark, in an ember tile. Original artwork; the same drawing is the favicon.
 */
export function LogoMark({ className, title }: { className?: string; title?: string }) {
  const gradient = useId()

  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("size-8 shrink-0", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#F97316" />
          <stop offset="1" stopColor="#C2410C" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={`url(#${gradient})`} />
      <rect x="8" y="10" width="3.6" height="12" rx="1" fill="#FFF7ED" />
      <rect x="13.2" y="7.5" width="3.6" height="14.5" rx="1" fill="#FFF7ED" fillOpacity="0.92" />
      <rect x="18.6" y="11.2" width="3.6" height="11.4" rx="1" fill="#FFF7ED" fillOpacity="0.85" transform="rotate(-12 20.4 22.6)" />
      <path d="M6.5 23.2h19a1 1 0 0 1 0 2H21l1.2 2h-12.4l1.2-2H6.5a1 1 0 0 1 0-2Z" fill="#FFEDD5" />
      <path d="m25 5.2.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7.7-1.8Z" fill="#FFF7ED" />
    </svg>
  )
}


export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("font-heading text-lg font-semibold tracking-tight", className)}>
      Library<span className="text-brand">Forge</span>
    </span>
  )
}


export function Logo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark title={compact ? "LibraryForge" : undefined} />
      {!compact && <Wordmark />}
    </span>
  )
}
