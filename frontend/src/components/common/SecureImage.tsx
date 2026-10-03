import { useState } from "react";

import { cn } from "@/lib/utils";
import { initials } from "@/lib/format";

/**
 * Images served by authenticated API endpoints (snapshots, face photos). The session cookie is sent
 * automatically; when the user may not see the image (403) or it was deleted by retention, a
 * neutral placeholder is shown instead.
 */
export function SecureImage({
  src,
  alt,
  fallbackName,
  className,
}: {
  src: string | null;
  alt: string;
  fallbackName?: string | null;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <div
        role="img"
        aria-label={alt}
        className={cn("bg-muted text-muted-foreground flex items-center justify-center text-xs font-medium", className)}
      >
        {initials(fallbackName)}
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
