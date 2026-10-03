import { ScanFace } from "lucide-react";

/** Wordmark until the Atlas/ITRC logo file is supplied (docs/open-questions.md P11). */
export function Brand() {
  return (
    <div className="flex items-center gap-2 px-2">
      <div className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-md">
        <ScanFace className="size-5" aria-hidden />
      </div>
      <div className="leading-tight">
        <p className="font-semibold">FaceTrack</p>
        <p className="text-muted-foreground text-xs">Atlas · ITRC</p>
      </div>
    </div>
  );
}
