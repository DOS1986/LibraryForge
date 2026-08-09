import {
  useState,
  type FormEvent,
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
  Label,
} from "@/components/ui/label"

import {
  login,
} from "@/lib/api"

import type {
  User,
} from "@/types"


interface LoginScreenProps {
  onLogin:
    (
      user: User
    ) => void
}


export function LoginScreen({
  onLogin,
}: LoginScreenProps) {
  const [
    email,
    setEmail,
  ] = useState("")

  const [
    password,
    setPassword,
  ] = useState("")

  const [
    error,
    setError,
  ] = useState<
    string | null
  >(null)

  const [
    submitting,
    setSubmitting,
  ] = useState(false)


  async function handleSubmit(
    event: FormEvent,
  ) {
    event.preventDefault()

    setError(null)
    setSubmitting(true)

    try {
      const result =
        await login(
          email,
          password,
        )

      onLogin(
        result.user
      )

    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to sign in."
      )

    } finally {
      setSubmitting(false)
    }
  }


  return (
    <main
      className="
        flex
        min-h-screen
        items-center
        justify-center
        bg-muted/30
        p-6
      "
    >
      <Card
        className="
          w-full
          max-w-md
        "
      >
        <CardHeader>
          <CardTitle
            className="
              text-2xl
            "
          >
            LibraryForge
          </CardTitle>

          <CardDescription>
            Sign in to manage your media libraries.
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form
            onSubmit={
              handleSubmit
            }
            className="
              space-y-4
            "
          >
            <div
              className="
                space-y-2
              "
            >
              <Label
                htmlFor="email"
              >
                Email
              </Label>

              <Input
                id="email"
                type="email"
                value={email}
                onChange={
                  (
                    event
                  ) =>
                    setEmail(
                      event
                        .target
                        .value
                    )
                }
                required
              />
            </div>

            <div
              className="
                space-y-2
              "
            >
              <Label
                htmlFor="password"
              >
                Password
              </Label>

              <Input
                id="password"
                type="password"
                value={password}
                onChange={
                  (
                    event
                  ) =>
                    setPassword(
                      event
                        .target
                        .value
                    )
                }
                required
              />
            </div>

            {error && (
              <p
                className="
                  text-sm
                  text-destructive
                "
              >
                {error}
              </p>
            )}

            <Button
              type="submit"
              className="
                w-full
              "
              disabled={
                submitting
              }
            >
              {
                submitting
                  ? "Signing In..."
                  : "Sign In"
              }
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
