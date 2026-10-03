import { FileSpreadsheet, Upload } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { useImportEmployees } from "@/hooks/useEmployees";
import { useJob } from "@/hooks/useJob";
import { showError } from "@/lib/forms";

interface ImportResult {
  created: number;
  updated: number;
  photos_accepted: number;
  photos_rejected: number;
  error_count: number;
  errors: { where: string; message: string }[];
}

function isImportResult(value: unknown): value is ImportResult {
  return typeof value === "object" && value !== null && "created" in value && "errors" in value;
}

/** FR-11: Excel/CSV of employees plus an optional ZIP of photos named by employee code. */
export function ImportDialog() {
  const [open, setOpen] = useState(false);
  const [sheet, setSheet] = useState<File | null>(null);
  const [zip, setZip] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const importEmployees = useImportEmployees();
  const job = useJob(jobId);
  const status = job.data?.data.status;
  const result = job.data?.data.result;

  const reset = () => {
    setSheet(null);
    setZip(null);
    setJobId(null);
  };

  const start = async () => {
    if (!sheet) return;
    try {
      const response = await importEmployees.mutateAsync({ sheet, photosZip: zip });
      setJobId(response.data.job_id);
    } catch (error) {
      showError(error);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <Upload aria-hidden /> Bulk import
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Bulk import employees</DialogTitle>
          <DialogDescription>
            Columns: employee_code, full_name, department_code, designation, shift, location, email, phone,
            status, consent_signed_at, hr_external_id. Existing codes are updated. Photos in the ZIP are
            named &lt;employee_code&gt;.jpg or &lt;employee_code&gt;_2.jpg and are enrolled only for
            employees with signed consent.
          </DialogDescription>
        </DialogHeader>
        {jobId === null ? (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="import-sheet">Employee sheet (.xlsx or .csv, up to 10 MB)</Label>
              <Input
                id="import-sheet"
                type="file"
                accept=".xlsx,.csv"
                onChange={(event) => setSheet(event.target.files?.[0] ?? null)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="import-zip">Photos (.zip, optional, up to 200 MB)</Label>
              <Input
                id="import-zip"
                type="file"
                accept=".zip"
                onChange={(event) => setZip(event.target.files?.[0] ?? null)}
              />
            </div>
          </div>
        ) : status === "succeeded" && isImportResult(result) ? (
          <div className="space-y-3 text-sm" role="status">
            <p>
              <strong>{result.created}</strong> created, <strong>{result.updated}</strong> updated,{" "}
              <strong>{result.photos_accepted}</strong> photos enrolled, <strong>{result.photos_rejected}</strong> photos
              rejected.
            </p>
            {result.error_count > 0 && (
              <div className="max-h-48 overflow-auto rounded-md border p-2">
                <p className="mb-1 font-medium">{result.error_count} problems</p>
                <ul className="text-muted-foreground space-y-1">
                  {result.errors.map((error, index) => (
                    <li key={index}>
                      <span className="font-mono">{error.where}</span>: {error.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : status === "failed" ? (
          <p role="alert" className="text-destructive text-sm">
            {job.data?.data.message ?? "The import failed."}
          </p>
        ) : (
          <div className="space-y-2" role="status">
            <p className="flex items-center gap-2 text-sm">
              <FileSpreadsheet className="size-4" aria-hidden /> Importing… this can take a few minutes for large files.
            </p>
            <Progress value={status === "running" ? 60 : 20} />
          </div>
        )}
        <DialogFooter>
          {jobId === null ? (
            <Button onClick={() => void start()} disabled={!sheet || importEmployees.isPending}>
              {importEmployees.isPending ? "Uploading…" : "Start import"}
            </Button>
          ) : (
            <Button variant="outline" onClick={() => setOpen(false)}>
              Close
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
