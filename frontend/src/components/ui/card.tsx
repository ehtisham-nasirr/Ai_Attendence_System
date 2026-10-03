import * as React from "react"
import { fwd } from "@/lib/forwardRef"
import { cn } from "@/lib/utils"

const Card = fwd(function Card({ className, ...props }: React.ComponentProps<"div">, ref: React.ForwardedRef<unknown>) {
  return (
    <div
      data-slot="card"
      className={cn(
        "flex flex-col gap-6 rounded-xl border bg-card py-6 text-card-foreground shadow-sm",
        className
      )}
      ref={ref as never}
      {...props}
    />
  )
})

const CardHeader = fwd(function CardHeader({ className, ...props }: React.ComponentProps<"div">, ref: React.ForwardedRef<unknown>) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "@container/card-header grid auto-rows-min grid-rows-[auto_auto] items-start gap-2 px-6 has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-6",
        className
      )}
      ref={ref as never}
      {...props}
    />
  )
})

const CardTitle = fwd(function CardTitle({ className, ...props }: React.ComponentProps<"div">, ref: React.ForwardedRef<unknown>) {
  return (
    <div
      data-slot="card-title"
      className={cn("leading-none font-semibold", className)}
      ref={ref as never}
      {...props}
    />
  )
})

const CardDescription = fwd(function CardDescription({ className, ...props }: React.ComponentProps<"div">, ref: React.ForwardedRef<unknown>) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-sm text-muted-foreground", className)}
      ref={ref as never}
      {...props}
    />
  )
})

const CardAction = fwd(function CardAction({ className, ...props }: React.ComponentProps<"div">, ref: React.ForwardedRef<unknown>) {
  return (
    <div
      data-slot="card-action"
      className={cn(
        "col-start-2 row-span-2 row-start-1 self-start justify-self-end",
        className
      )}
      ref={ref as never}
      {...props}
    />
  )
})

const CardContent = fwd(function CardContent({ className, ...props }: React.ComponentProps<"div">, ref: React.ForwardedRef<unknown>) {
  return (
    <div
      data-slot="card-content"
      className={cn("px-6", className)}
      ref={ref as never}
      {...props}
    />
  )
})

const CardFooter = fwd(function CardFooter({ className, ...props }: React.ComponentProps<"div">, ref: React.ForwardedRef<unknown>) {
  return (
    <div
      data-slot="card-footer"
      className={cn("flex items-center px-6 [.border-t]:pt-6", className)}
      ref={ref as never}
      {...props}
    />
  )
})

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardAction,
  CardDescription,
  CardContent,
}
