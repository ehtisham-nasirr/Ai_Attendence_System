import * as React from "react"
import { fwd } from "@/lib/forwardRef"
import { cn } from "@/lib/utils"

const Table = fwd(function Table({ className, ...props }: React.ComponentProps<"table">, ref: React.ForwardedRef<unknown>) {
  return (
    <div
      data-slot="table-container"
      className="relative w-full overflow-x-auto"
    >
      <table
        data-slot="table"
        className={cn("w-full caption-bottom text-sm", className)}
        ref={ref as never}
      {...props}
      />
    </div>
  )
})

const TableHeader = fwd(function TableHeader({ className, ...props }: React.ComponentProps<"thead">, ref: React.ForwardedRef<unknown>) {
  return (
    <thead
      data-slot="table-header"
      className={cn("[&_tr]:border-b", className)}
      ref={ref as never}
      {...props}
    />
  )
})

const TableBody = fwd(function TableBody({ className, ...props }: React.ComponentProps<"tbody">, ref: React.ForwardedRef<unknown>) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      ref={ref as never}
      {...props}
    />
  )
})

const TableFooter = fwd(function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">, ref: React.ForwardedRef<unknown>) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t bg-muted/50 font-medium [&>tr]:last:border-b-0",
        className
      )}
      ref={ref as never}
      {...props}
    />
  )
})

const TableRow = fwd(function TableRow({ className, ...props }: React.ComponentProps<"tr">, ref: React.ForwardedRef<unknown>) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-b transition-colors hover:bg-muted/50 has-aria-expanded:bg-muted/50 data-[state=selected]:bg-muted",
        className
      )}
      ref={ref as never}
      {...props}
    />
  )
})

const TableHead = fwd(function TableHead({ className, ...props }: React.ComponentProps<"th">, ref: React.ForwardedRef<unknown>) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "h-10 px-2 text-left align-middle font-medium whitespace-nowrap text-foreground [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
        className
      )}
      ref={ref as never}
      {...props}
    />
  )
})

const TableCell = fwd(function TableCell({ className, ...props }: React.ComponentProps<"td">, ref: React.ForwardedRef<unknown>) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "p-2 align-middle whitespace-nowrap [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
        className
      )}
      ref={ref as never}
      {...props}
    />
  )
})

const TableCaption = fwd(function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">, ref: React.ForwardedRef<unknown>) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-sm text-muted-foreground", className)}
      ref={ref as never}
      {...props}
    />
  )
})

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
