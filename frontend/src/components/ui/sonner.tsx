import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
} from "lucide-react"
import { Toaster as Sonner, type ToasterProps } from "sonner"

import { useTheme } from "@/hooks/useTheme"

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme } = useTheme()

  return (
    <Sonner
      theme={theme}
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
          // richColors: use the theme's status tokens instead of Sonner's built-in palette.
          "--success-bg": "color-mix(in oklab, var(--status-ok) 10%, var(--popover))",
          "--success-border": "color-mix(in oklab, var(--status-ok) 30%, var(--popover))",
          "--success-text": "var(--status-ok)",
          "--info-bg": "color-mix(in oklab, var(--status-info) 10%, var(--popover))",
          "--info-border": "color-mix(in oklab, var(--status-info) 30%, var(--popover))",
          "--info-text": "var(--status-info)",
          "--warning-bg": "color-mix(in oklab, var(--status-warn) 10%, var(--popover))",
          "--warning-border": "color-mix(in oklab, var(--status-warn) 30%, var(--popover))",
          "--warning-text": "var(--status-warn)",
          "--error-bg": "color-mix(in oklab, var(--status-bad) 10%, var(--popover))",
          "--error-border": "color-mix(in oklab, var(--status-bad) 30%, var(--popover))",
          "--error-text": "var(--status-bad)",
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }
