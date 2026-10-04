import type { FieldValues, Path, UseFormReturn } from "react-hook-form";
import { toast } from "sonner";

import { ApiError, toApiError } from "@/api/client";

/**
 * Shows an API error on a form (standards/09): field errors go under their inputs, anything else
 * becomes a toast. Returns the normalised error.
 */
export function showFormError<T extends FieldValues>(form: UseFormReturn<T>, error: unknown): ApiError {
  const apiError = toApiError(error);
  const fields = Object.keys(form.getValues());
  let placed = false;
  const unplaced: string[] = [];
  for (const [field, messages] of Object.entries(apiError.fieldErrors)) {
    if (fields.includes(field)) {
      form.setError(field as Path<T>, { type: "server", message: messages.join(" ") });
      placed = true;
    } else {
      unplaced.push(...messages);
    }
  }
  // Errors that belong to no input (e.g. "Check-out must be after check-in") must still be readable.
  if (unplaced.length) toast.error(unplaced.join(" "));
  else if (!placed) toast.error(apiError.message);
  return apiError;
}

export function showError(error: unknown): void {
  toast.error(toApiError(error).message);
}
