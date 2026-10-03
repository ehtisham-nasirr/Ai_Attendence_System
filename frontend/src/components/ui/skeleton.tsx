import * as React from "react"
import { fwd } from "@/lib/forwardRef"
import { cn } from "@/lib/utils"

const Skeleton = fwd(function Skeleton({ className, ...props }: React.ComponentProps<"div">, ref: React.ForwardedRef<unknown>) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-md bg-accent", className)}
      ref={ref as never}
      {...props}
    />
  )
})

export { Skeleton }
