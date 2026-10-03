import { FileSpreadsheet, FileText } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { getJob } from "@/api/generated/endpoints";
import type { ReportType } from "@/api/generated/model";
import { Button } from "@/components/ui/button";
import { downloadJobFile, useStartExport, type ReportFilters } from "@/hooks/useReports";
import { showError } from "@/lib/forms";
import { exportFileName } from "@/lib/reports";

const POLL_MS = 1_500;
const MAX_WAIT_MS = 10 * 60_000;

/** FR-31: Excel / PDF export as a background job (202); the file downloads when the job finishes. */
export function ExportButtons({ reportType, params }: { reportType: ReportType; params: ReportFilters }) {
  const start = useStartExport();
  const [running, setRunning] = useState<"xlsx" | "pdf" | null>(null);

  const run = async (format: "xlsx" | "pdf") => {
    setRunning(format);
    try {
      const jobId = await start.mutateAsync({ reportType, params, format });
      for (let waited = 0; waited < MAX_WAIT_MS; waited += POLL_MS) {
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
        const job = (await getJob(jobId)).data;
        if (job.status === "failed") throw new Error(job.message ?? "The export failed.");
        if (job.status === "succeeded") {
          await downloadJobFile(jobId, exportFileName(reportType, params.date_from, params.date_to, format));
          toast.success(`Exported ${job.message ?? ""}.`);
          return;
        }
      }
      throw new Error("The export is taking too long. Try a shorter period.");
    } catch (error) {
      showError(error);
    } finally {
      setRunning(null);
    }
  };

  return (
    <div className="flex gap-2">
      <Button variant="outline" onClick={() => void run("xlsx")} disabled={running !== null}>
        <FileSpreadsheet aria-hidden /> {running === "xlsx" ? "Preparing Excel…" : "Export Excel"}
      </Button>
      <Button variant="outline" onClick={() => void run("pdf")} disabled={running !== null}>
        <FileText aria-hidden /> {running === "pdf" ? "Preparing PDF…" : "Export PDF"}
      </Button>
    </div>
  );
}
