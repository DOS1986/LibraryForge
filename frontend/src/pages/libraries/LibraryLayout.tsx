import {
  Navigate,
  Outlet,
  useParams,
} from "react-router-dom"

import {
  Card,
  CardContent,
} from "@/components/ui/card"

import {
  useAppOutlet,
} from "@/lib/route-context"

import type {
  LibraryOutletContext,
} from "@/lib/route-context"


export function LibraryLayout() {
  const {
    libraryId,
  } = useParams()

  const {
    libraries,
    librariesLoading,
    refreshLibraries,
  } = useAppOutlet()

  if (librariesLoading) {
    return (
      <Card>
        <CardContent
          className="
            py-12
            text-center
            text-muted-foreground
          "
        >
          Loading library...
        </CardContent>
      </Card>
    )
  }

  if (!libraryId) {
    return (
      <Navigate
        to="/"
        replace
      />
    )
  }

  const library =
    libraries.find(
      (
        item
      ) =>
        item.id
        === libraryId
    )

  if (!library) {
    return (
      <Card>
        <CardContent
          className="
            py-12
            text-center
            text-muted-foreground
          "
        >
          Library not found.
        </CardContent>
      </Card>
    )
  }

  const context:
    LibraryOutletContext = {
      library,
      refreshLibraries,
    }

  return (
    <Outlet
      context={
        context
      }
    />
  )
}
