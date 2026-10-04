import * as React from "react"
import { fwd } from "@/lib/forwardRef"
import { cn } from "@/lib/utils"

const Textarea = fwd(function Textarea({ className, ...props }: React.ComponentProps<"textarea">, ref: React.ForwardedRef<unknown>) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full rounded-md border border-input bg-card px-3 py-2 text-base shadow-xs transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/30 dark:aria-invalid:ring-destructive/40",
        className
      )}
      ref={ref as never}
      {...props}
    />
  )
})

export { Textarea }
