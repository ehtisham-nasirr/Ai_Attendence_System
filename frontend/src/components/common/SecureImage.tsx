import { ImageOff } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";
import { initials } from "@/lib/format";

/**
 * Images served by authenticated API endpoints (snapshots, face photos). The session cookie is sent
 * automatically; when the user may not see the image (403) or it was deleted by retention, a
 * neutral placeholder is shown instead: initials of `fallbackName`, or, when `unavailableLabel` is
 * set, an icon with that text (e.g. "No photo"), which is also added to the accessible name.
 */
export function SecureImage({
  src,
  alt,
  fallbackName,
  unavailableLabel,
  className,
}: {
  src: string | null;
  alt: string;
  fallbackName?: string | null;
  unavailableLabel?: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <div
        role="img"
        aria-label={unavailableLabel ? `${alt} (${unavailableLabel})` : alt}
        className={cn(
          "bg-muted text-muted-foreground flex flex-col items-center justify-center gap-1 text-xs font-medium",
          className,
        )}
      >
        {unavailableLabel ? (
          <>
            <ImageOff className="size-4" aria-hidden />
            <span className="px-1 text-center leading-tight">{unavailableLabel}</span>
          </>
        ) : (
          initials(fallbackName)
        )}
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      decoding="async"
      className={cn("object-cover", className)}
      onError={() => setFailed(true)}
    />
  );
}
