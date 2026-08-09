import type {
  ComponentProps,
} from "react"

import {
  DialogContent,
  DialogHeader,
} from "@/components/ui/dialog"

import {
  cn,
} from "@/lib/utils"


export function ScrollableDialogContent({
  className,
  ...props
}: ComponentProps<
  typeof DialogContent
>) {
  return (
    <DialogContent
      className={
        cn(
          `
            flex
            h-[85vh]
            max-h-[85vh]
            !w-[calc(100vw-2rem)]
            !max-w-[1400px]
            flex-col
            overflow-hidden
            p-0
            sm:!max-w-[1400px]
          `,
          className,
        )
      }
      {...props}
    />
  )
}


export function ScrollableDialogHeader({
  className,
  ...props
}: ComponentProps<
  typeof DialogHeader
>) {
  return (
    <DialogHeader
      className={
        cn(
          `
            shrink-0
            border-b
            px-6
            py-5
            pr-12
          `,
          className,
        )
      }
      {...props}
    />
  )
}


export function ScrollableDialogBody({
  className,
  ...props
}: ComponentProps<"div">) {
  return (
    <div
      className={
        cn(
          `
            min-h-0
            min-w-0
            flex-1
            overflow-y-auto
            overflow-x-hidden
            px-6
            py-5
          `,
          className,
        )
      }
      {...props}
    />
  )
}
