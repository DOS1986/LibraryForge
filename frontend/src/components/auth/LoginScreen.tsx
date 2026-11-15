import { useState, type FormEvent } from "react"

import { Eye, EyeOff, FileCode2, FolderSymlink, Loader2, ShieldCheck } from "lucide-react"

import { LogoMark, Wordmark } from "@/components/brand/Logo"
import { ThemeMenu } from "@/components/app/ThemeMenu"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

import { login } from "@/lib/api"

import type { User } from "@/types"


interface LoginScreenProps {
  onLogin: (user: User) => void
}


const HIGHLIGHTS = [
  { icon: ShieldCheck, title: "Ratings for every title", text: "Rate movies, shows, and channels so parental controls just work." },
  { icon: FileCode2, title: "NFOs and artwork, your way", text: "Metadata written beside your files, in the layout your media server reads." },
  { icon: FolderSymlink, title: "Your files stay put", text: "Review every change before it's applied. Nothing is moved without you." },
]


export function LoginScreen({ onLogin }: LoginScreenProps) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    try {
      const result = await login(email, password)
      onLogin(result.user)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to sign in.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="grid min-h-svh lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      {/* Brand panel */}
      <section className="relative hidden overflow-hidden bg-[oklch(0.19_0.012_45)] text-[oklch(0.97_0.004_75)] lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-32 -left-24 size-[34rem] rounded-full bg-[radial-gradient(circle,oklch(0.65_0.19_41/0.45),transparent_65%)] blur-2xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -right-40 bottom-[-12rem] size-[36rem] rounded-full bg-[radial-gradient(circle,oklch(0.75_0.157_55/0.25),transparent_65%)] blur-2xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(to_right,white_1px,transparent_1px),linear-gradient(to_bottom,white_1px,transparent_1px)] [background-size:44px_44px]"
        />

        <div className="relative flex items-center gap-3">
          <LogoMark className="size-9" />
          <span className="font-heading text-xl font-semibold tracking-tight">
            Library<span className="text-[oklch(0.8_0.15_55)]">Forge</span>
          </span>
        </div>

        <div className="relative max-w-lg space-y-8">
          <div className="space-y-3">
            <h1 className="text-4xl leading-tight font-semibold tracking-tight">
              Your media. Your metadata.
              <br />
              <span className="text-[oklch(0.8_0.15_55)]">Your structure.</span>
            </h1>
            <p className="text-base text-[oklch(0.82_0.01_70)]">
              Organize, rate, and enrich your libraries, then hand your media server exactly what it expects.
            </p>
          </div>
          <ul className="space-y-4">
            {HIGHLIGHTS.map(item => (
              <li key={item.title} className="flex gap-3">
                <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/8 ring-1 ring-white/10">
                  <item.icon className="size-4 text-[oklch(0.8_0.15_55)]" />
                </span>
                <span>
                  <span className="block font-medium">{item.title}</span>
                  <span className="block text-sm text-[oklch(0.78_0.01_70)]">{item.text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-[oklch(0.7_0.01_70)]">Self-hosted. Your data never leaves your server.</p>
      </section>

      {/* Sign-in form */}
      <section className="relative flex flex-col bg-background">
        <div className="flex items-center justify-between p-4 lg:justify-end">
          <span className="flex items-center gap-2 lg:hidden">
            <LogoMark className="size-7" />
            <Wordmark className="text-base" />
          </span>
          <ThemeMenu />
        </div>

        <div className="flex flex-1 items-center justify-center px-6 pb-16">
          <div className="w-full max-w-sm space-y-8">
            <div className="space-y-2">
              <h2 className="text-2xl font-semibold">Welcome back</h2>
              <p className="text-sm text-muted-foreground">Sign in to manage your media libraries.</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5" noValidate={false}>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  autoFocus
                  value={email}
                  onChange={event => setEmail(event.target.value)}
                  required
                  className="h-10"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    value={password}
                    onChange={event => setPassword(event.target.value)}
                    required
                    className="h-10 pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(value => !value)}
                    className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-lg text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                  >
                    {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
              </div>

              {error && (
                <p className="rounded-lg border border-destructive/30 bg-destructive/8 px-3 py-2 text-sm text-destructive" role="alert">
                  {error}
                </p>
              )}

              <Button type="submit" size="lg" className="w-full" disabled={submitting}>
                {submitting && <Loader2 className="animate-spin" />}
                {submitting ? "Signing in..." : "Sign in"}
              </Button>
            </form>
          </div>
        </div>
      </section>
    </main>
  )
}
