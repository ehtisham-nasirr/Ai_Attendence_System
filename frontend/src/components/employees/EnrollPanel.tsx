import { AlertTriangle, CheckCircle2, ImagePlus, X, XCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";

import type { EmployeeOut, PhotoResult } from "@/api/generated/model";
import { WebcamCapture } from "@/components/employees/WebcamCapture";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useFaceMutations } from "@/hooks/useEmployees";
import { formatPercent } from "@/lib/format";
import { showError } from "@/lib/forms";
import { cn } from "@/lib/utils";

const MAX_FILES = 10;
const MAX_BYTES = 5 * 1024 * 1024;
const TYPES = new Set(["image/jpeg", "image/png"]);

interface Pending {
  file: File;
  url: string;
  source: "upload" | "webcam";
}

/** §13 screen 5, Enroll tab (FR-8, FR-9, FR-10): drag-drop upload or webcam capture. */
export function EnrollPanel({ employee }: { employee: EmployeeOut }) {
  const { upload } = useFaceMutations(employee.id);
  const [pending, setPending] = useState<Pending[]>([]);
  const [rejected, setRejected] = useState<string[]>([]);
  const [results, setResults] = useState<PhotoResult[] | null>(null);
  const [dragging, setDragging] = useState(false);
  const hasConsent = Boolean(employee.consent_signed_at);

  // Preview URLs are revoked when removed, after upload, and when the panel unmounts.
  const pendingRef = useRef(pending);
  useEffect(() => {
    pendingRef.current = pending;
  }, [pending]);
  useEffect(() => () => pendingRef.current.forEach((p) => URL.revokeObjectURL(p.url)), []);

  const add = (files: File[], source: Pending["source"]) => {
    const problems: string[] = [];
    const accepted: Pending[] = [];
    for (const file of files) {
      if (!TYPES.has(file.type)) problems.push(`${file.name}: only JPEG or PNG photos`);
      else if (file.size > MAX_BYTES) problems.push(`${file.name}: larger than 5 MB`);
      else accepted.push({ file, url: URL.createObjectURL(file), source });
    }
    setRejected(problems);
    setResults(null);
    setPending((current) => {
      const room = MAX_FILES - current.length;
      if (accepted.length > room) problems.push(`Only ${MAX_FILES} photos can be uploaded at once.`);
      accepted.slice(room).forEach((p) => URL.revokeObjectURL(p.url));
      return [...current, ...accepted.slice(0, Math.max(0, room))];
    });
  };

  const removePending = (index: number) =>
    setPending((current) => {
      URL.revokeObjectURL(current[index].url);
      return current.filter((_, i) => i !== index);
    });

  const submit = async () => {
    // One request per source so each photo is recorded with how it was taken.
    const groups = (["upload", "webcam"] as const)
      .map((source) => ({ source, files: pending.filter((p) => p.source === source).map((p) => p.file) }))
      .filter((group) => group.files.length > 0);
    try {
      const all: PhotoResult[] = [];
      for (const group of groups) all.push(...(await upload.mutateAsync(group)).data.results);
      setResults(all);
      pending.forEach((p) => URL.revokeObjectURL(p.url));
      setPending([]);
    } catch (error) {
      showError(error);
    }
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    add(Array.from(event.dataTransfer.files), "upload");
  };

  const summary = useMemo(() => {
    if (!results) return null;
    const ok = results.filter((r) => r.accepted).length;
    return `${ok} of ${results.length} photos enrolled.`;
  }, [results]);

  if (!hasConsent) {
    return (
      <div role="alert" className="border-status-warn/40 bg-status-warn/10 flex gap-3 rounded-lg border p-4 text-sm">
        <AlertTriangle className="text-status-warn size-5 shrink-0" aria-hidden />
        <div>
          <p className="font-medium">Signed consent is required before enrollment</p>
          <p className="text-muted-foreground">
            Record the date the employee signed the biometric consent form on the Details tab, then return here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">
        Use 3 to 10 clear photos: one face, looking at the camera, even light, face at least 112 px wide. Each photo is
        checked before it is added ({employee.enrolled_photos ?? 0} enrolled now).
      </p>
      <Tabs defaultValue="upload">
        <TabsList>
          <TabsTrigger value="upload">Upload photos</TabsTrigger>
          <TabsTrigger value="webcam">Webcam</TabsTrigger>
        </TabsList>
        <TabsContent value="upload">
          <label
            htmlFor="enroll-files"
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center text-sm",
              dragging ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50",
            )}
          >
            <ImagePlus className="text-muted-foreground size-8" aria-hidden />
            <span className="font-medium">Drop photos here or click to choose</span>
            <span className="text-muted-foreground">JPEG or PNG, up to 5 MB each</span>
            <input
              id="enroll-files"
              type="file"
              accept="image/jpeg,image/png"
              multiple
              className="sr-only"
              onChange={(event) => {
                add(Array.from(event.target.files ?? []), "upload");
                event.target.value = "";
              }}
            />
          </label>
        </TabsContent>
        <TabsContent value="webcam">
          <WebcamCapture onCapture={(file) => add([file], "webcam")} disabled={pending.length >= MAX_FILES} />
        </TabsContent>
      </Tabs>

      {rejected.length > 0 && (
        <ul role="alert" className="text-destructive space-y-1 text-sm">
          {rejected.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}

      {pending.length > 0 && (
        <div className="space-y-3">
          <ul className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-10">
            {pending.map((item, index) => (
              <li key={item.url} className="relative overflow-hidden rounded-md border">
                <img src={item.url} alt={`Photo ${index + 1} to enroll`} className="aspect-square w-full object-cover" />
                <button
                  type="button"
                  className="bg-background/90 absolute top-1 right-1 rounded-full p-0.5"
                  aria-label={`Remove photo ${index + 1}`}
                  onClick={() => removePending(index)}
                >
                  <X className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
          <Button onClick={() => void submit()} disabled={upload.isPending}>
            {upload.isPending ? "Checking photos…" : `Enroll ${pending.length} photo${pending.length === 1 ? "" : "s"}`}
          </Button>
        </div>
      )}

      {results && (
        <div className="space-y-2" role="status">
          <p className="font-medium">{summary}</p>
          <ul className="divide-y rounded-lg border">
            {results.map((result, index) => (
              <li key={`${result.filename}-${index}`} className="flex items-start gap-3 p-3 text-sm">
                {result.accepted ? (
                  <CheckCircle2 className="text-status-ok mt-0.5 size-4 shrink-0" aria-label="Accepted" />
                ) : (
                  <XCircle className="text-status-bad mt-0.5 size-4 shrink-0" aria-label="Rejected" />
                )}
                <div className="min-w-0">
                  <p className="truncate font-medium">{result.filename}</p>
                  <p className="text-muted-foreground">
                    {result.accepted
                      ? `Accepted · quality ${formatPercent(result.quality_score ?? null)}`
                      : (result.rejection_reason ?? "Rejected")}
                  </p>
                  {result.possible_duplicates && result.possible_duplicates.length > 0 && (
                    <p className="text-status-warn">
                      Very similar to: {result.possible_duplicates.join(", ")}. Check this is not the same person
                      enrolled twice.
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
