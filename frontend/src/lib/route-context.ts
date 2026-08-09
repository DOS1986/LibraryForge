import {
  useOutletContext,
} from "react-router-dom"

import type {
  Library,
} from "@/types"


export interface AppOutletContext {
  libraries: Library[]
  librariesLoading: boolean
  refreshLibraries:
    () => Promise<void>
}


export interface LibraryOutletContext {
  library: Library
  refreshLibraries:
    () => Promise<void>
}


export function useAppOutlet() {
  return useOutletContext<
    AppOutletContext
  >()
}


export function useLibraryOutlet() {
  return useOutletContext<
    LibraryOutletContext
  >()
}
