
import * as React from "react"
import { fwd } from "@/lib/forwardRef"
import { cn } from "@/lib/utils"
import { Popover as PopoverPrimitive } from "radix-ui"

function Popover({
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Root>) {
  return <PopoverPrimitive.Root data-slot="popover" {...props} />
}

const PopoverTrigger = fwd(function PopoverTrigger({
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Trigger>, ref: React.ForwardedRef<unknown>) {
  return <PopoverPrimitive.Trigger data-slot="popover-trigger" ref={ref as never}
      {...props} />
})

const PopoverContent = fwd(function PopoverContent({
  className,
  align = "center",
  sideOffset = 4,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>, ref: React.ForwardedRef<unknown>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        data-slot="popover-content"
        align={align}
        sideOffset={sideOffset}
        className={cn(
          "z-50 w-72 origin-(--radix-popover-content-transform-origin) rounded-md border bg-popover p-4 text-popover-foreground shadow-md outline-hidden data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          className
        )}
        ref={ref as never}
      {...props}
      />
    </PopoverPrimitive.Portal>
  )
})

const PopoverAnchor = fwd(function PopoverAnchor({
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Anchor>, ref: React.ForwardedRef<unknown>) {
  return <PopoverPrimitive.Anchor data-slot="popover-anchor" ref={ref as never}
      {...props} />
})

const PopoverHeader = fwd(function PopoverHeader({ className, ...props }: React.ComponentProps<"div">, ref: React.ForwardedRef<unknown>) {
  return (
    <div
      data-slot="popover-header"
      className={cn("flex flex-col gap-1 text-sm", className)}
      ref={ref as never}
      {...props}
    />
  )
})

const PopoverTitle = fwd(function PopoverTitle({ className, ...props }: React.ComponentProps<"h2">, ref: React.ForwardedRef<unknown>) {
  return (
    <div
      data-slot="popover-title"
      className={cn("font-medium", className)}
      ref={ref as never}
      {...props}
    />
  )
})

const PopoverDescription = fwd(function PopoverDescription({
  className,
  ...props
}: React.ComponentProps<"p">, ref: React.ForwardedRef<unknown>) {
  return (
    <p
      data-slot="popover-description"
      className={cn("text-muted-foreground", className)}
      ref={ref as never}
      {...props}
    />
  )
})

export {
  Popover,
  PopoverTrigger,
  PopoverContent,
  PopoverAnchor,
  PopoverHeader,
  PopoverTitle,
  PopoverDescription,
}
