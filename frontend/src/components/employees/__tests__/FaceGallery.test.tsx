import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { FaceOut } from "@/api/generated/model";
import { FaceGallery } from "@/components/employees/FaceGallery";
import { ok } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";

function face(id: number, source: FaceOut["source"], quality = 0.9): FaceOut {
  return { id, quality_score: quality, source, model_name: "sface", is_active: true, created_at: "2026-10-05T10:00:00Z" };
}

describe("Face gallery (§13 screen 5, Q64)", () => {
  it("shows enrollment photos and assigned camera photos under their own headings", async () => {
    server.use(
      http.get("*/api/v1/employees/7/faces", () =>
        HttpResponse.json(ok([face(1, "webcam"), face(2, "review", 0), face(3, "review", 0)])),
      ),
      http.get("*/api/v1/employees/7/faces/*/image", () => new HttpResponse(null, { status: 404 })),
    );
    renderWithProviders(<FaceGallery employeeId={7} onEnroll={vi.fn()} />);

    const enrolled = await screen.findByRole("region", { name: "Enrollment photos (1)" });
    expect(within(enrolled).getByText("Quality 90%")).toBeInTheDocument();
    const assigned = screen.getByRole("region", { name: "Assigned photos (2)" });
    expect(within(assigned).getAllByText("From a camera")).toHaveLength(2);
    expect(within(assigned).getAllByRole("button", { name: /Delete face photo/ })).toHaveLength(2);
  });
});
