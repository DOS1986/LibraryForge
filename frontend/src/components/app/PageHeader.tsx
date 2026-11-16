import type { ReactNode } from "react"

import { cn } from "@/lib/utils"


/** The title block at the top of every page: optional eyebrow, title, description, and actions. */
export function PageHeader({
  title,
  eyebrow,
  description,
  icon,
  actions,
  className,
}: {
  title: ReactNode
  eyebrow?: ReactNode
  description?: ReactNode
  icon?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <header className={cn("flex flex-wrap items-start justify-between gap-4", className)}>
      <div className="flex min-w-0 items-start gap-3">
        {icon && (
          <div className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary dark:bg-primary/15">
            {icon}
          </div>
        )}
        <div className="min-w-0 space-y-1">
          {eyebrow && <div className="text-xs font-medium text-muted-foreground">{eyebrow}</div>}
          <h1 className="text-2xl font-semibold">{title}</h1>
          {description && <div className="max-w-3xl text-sm text-muted-foreground">{description}</div>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}


/** A small stat tile for summary rows. */
export function StatTile({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: ReactNode
  value: ReactNode
  hint?: ReactNode
  tone?: "default" | "brand" | "warning" | "success"
}) {
  const accent = {
    default: "",
    brand: "before:bg-brand",
    warning: "before:bg-warning",
    success: "before:bg-success",
  }[tone]

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border bg-card p-4 shadow-xs",
        tone !== "default" && "before:absolute before:inset-y-0 before:left-0 before:w-1",
        accent,
      )}
    >
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </div>
  )
}
