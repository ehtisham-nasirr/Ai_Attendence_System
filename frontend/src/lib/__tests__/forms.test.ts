import { renderHook } from "@testing-library/react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { showFormError } from "@/lib/forms";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

function formWith(values: Record<string, string>) {
  return renderHook(() => useForm<Record<string, string>>({ defaultValues: values })).result.current;
}

describe("showFormError", () => {
  afterEach(() => vi.mocked(toast.error).mockClear());

  it("puts field errors under their inputs without a toast", () => {
    const form = formWith({ reason: "" });
    showFormError(form, new ApiError(422, "Validation failed.", { reason: ["Too short"] }));
    expect(form.getFieldState("reason").error?.message).toBe("Too short");
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("shows errors that belong to no input in the toast instead of only 'Validation failed.'", () => {
    const form = formWith({ reason: "x" });
    showFormError(form, new ApiError(422, "Validation failed.", { body: ["Check-out must be after check-in"] }));
    expect(toast.error).toHaveBeenCalledWith("Check-out must be after check-in");
  });

  it("falls back to the general message when there are no field errors", () => {
    const form = formWith({ reason: "x" });
    showFormError(form, new ApiError(409, "This day already has a record."));
    expect(toast.error).toHaveBeenCalledWith("This day already has a record.");
  });
});
