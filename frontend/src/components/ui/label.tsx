import * as React from "react"
import { fwd } from "@/lib/forwardRef"
import { cn } from "@/lib/utils"
import { Label as LabelPrimitive } from "radix-ui"

const Label = fwd(function Label({
  className,
  ...props
}: React.ComponentProps<typeof LabelPrimitive.Root>, ref: React.ForwardedRef<unknown>) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn(
        "flex items-center gap-2 text-sm leading-none font-medium select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
        className
      )}
      ref={ref as never}
      {...props}
    />
  )
})

export { Label }
