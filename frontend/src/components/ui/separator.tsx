
import * as React from "react"
import { fwd } from "@/lib/forwardRef"
import { cn } from "@/lib/utils"
import { Separator as SeparatorPrimitive } from "radix-ui"

const Separator = fwd(function Separator({
  className,
  orientation = "horizontal",
  decorative = true,
  ...props
}: React.ComponentProps<typeof SeparatorPrimitive.Root>, ref: React.ForwardedRef<unknown>) {
  return (
    <SeparatorPrimitive.Root
      data-slot="separator"
      decorative={decorative}
      orientation={orientation}
      className={cn(
        "shrink-0 bg-border data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-px",
        className
      )}
      ref={ref as never}
      {...props}
    />
  )
})

export { Separator }
