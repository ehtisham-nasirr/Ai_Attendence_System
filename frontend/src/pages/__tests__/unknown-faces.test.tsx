import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { UnknownFaceBulkResult, UnknownFaceGroupOut, UnknownFaceOut, UserProfile } from "@/api/generated/model";
import { applyLiveMessage } from "@/lib/live";
import { UnknownFacesPage } from "@/pages/unknown-faces/UnknownFacesPage";
import { employee, hrUser, ok, page } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";

// Synthetic data only: ids and timestamps, no real faces (thumbnails are never fetched in jsdom).
function face(id: number, overrides: Partial<UnknownFaceOut> = {}): UnknownFaceOut {
  return {
    id,
    recognition_event_id: 1000 + id,
    captured_at: "2026-10-04T05:00:00Z",
    camera_id: 3,
    camera_name: "Gate 1",
    liveness_score: 0.9,
    review_status: "pending",
    assigned_employee_id: null,
    reviewed_at: null,
    snapshot_available: true,
    group_id: null,
    ...overrides,
  };
}

/** Face ids newest first, as the API sends them. */
function ids(from: number, to: number): number[] {
  return Array.from({ length: to - from + 1 }, (_, index) => to - index);
}

function group(groupId: number, faceIds: number[], overrides: Partial<UnknownFaceGroupOut> = {}): UnknownFaceGroupOut {
  return {
    group_id: groupId,
    face_count: faceIds.length,
    pending_count: faceIds.length,
    first_seen_at: "2026-10-04T04:00:00Z",
    last_seen_at: "2026-10-04T06:30:00Z",
    camera_ids: [3],
    camera_names: ["Gate 1"],
    face_ids: faceIds,
    samples: faceIds.slice(0, 8).map((id) => face(id)),
    ...overrides,
  };
}

function groupsPage(
  data: UnknownFaceGroupOut[],
  { total = data.length, pageNumber = 1, facesTotal }: { total?: number; pageNumber?: number; facesTotal?: number } = {},
) {
  const grouped = data.reduce((sum, item) => sum + item.face_count, 0);
  const faces = facesTotal ?? grouped;
  return {
    success: true,
    message: "Unknown-face groups retrieved.",
    data,
    pagination: { page: pageNumber, page_size: 12, total },
    grouping: { faces_total: faces, faces_grouped: grouped, max_faces: 5000, truncated: faces > grouped },
  };
}

function bulkResult(overrides: Partial<UnknownFaceBulkResult>): UnknownFaceBulkResult {
  return {
    action: "assign",
    processed_ids: [],
    skipped: [],
    attendance_updated: false,
    added_to_gallery: false,
    gallery_face_id: null,
    gallery_rejection_reason: null,
    ...overrides,
  };
}

/** Serves `respond` for the groups endpoint and records every request's query string. */
function serveGroups(respond: (params: URLSearchParams) => ReturnType<typeof groupsPage>) {
  const requests: URLSearchParams[] = [];
  server.use(
    http.get("*/api/v1/cameras", () => HttpResponse.json(page([{ id: 3, name: "Gate 1" }]))),
    http.get("*/api/v1/unknown-faces/groups", ({ request }) => {
      const params = new URL(request.url).searchParams;
      requests.push(params);
      return HttpResponse.json(respond(params));
    }),
  );
  return requests;
}

function captureBulk(result: UnknownFaceBulkResult, message: string) {
  const bodies: unknown[] = [];
  server.use(
    http.post("*/api/v1/unknown-faces/bulk", async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json(ok(result, message));
    }),
  );
  return bodies;
}

const owner = group(101, ids(101, 130), { camera_ids: [3, 4], camera_names: ["Gate 1", "Lobby"] });
const visitor = group(7, [7], { first_seen_at: "2026-10-04T08:15:00Z", last_seen_at: "2026-10-04T08:15:00Z" });

describe("Unknown faces screen (§13 screen 9, FR-27, Q58)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows each group once, with its count, first/last seen, cameras and up to 8 thumbnails", async () => {
    const requests = serveGroups(() => groupsPage([owner, visitor]));
    renderWithProviders(<UnknownFacesPage />, { route: "/unknown-faces" });

    const cards = await screen.findAllByRole("article");
    expect(cards).toHaveLength(2);
    expect(screen.getAllByText("30 sightings")).toHaveLength(1);
    expect(screen.getByText("31 faces in 2 groups")).toBeInTheDocument();

    const ownerCard = within(cards[0]);
    expect(ownerCard.getByText("Showing 8 of 30 faces.")).toBeInTheDocument();
    expect(ownerCard.getByText("04 Oct 2026, 09:00")).toBeInTheDocument(); // first seen, Pakistan time
    expect(ownerCard.getByText("04 Oct 2026, 11:30")).toBeInTheDocument(); // last seen
    expect(ownerCard.getByText("Gate 1, Lobby")).toBeInTheDocument();
    const thumbnails = ownerCard.getAllByRole("img");
    expect(thumbnails).toHaveLength(8);
    expect(thumbnails[0]).toHaveAttribute("src", "/api/v1/unknown-faces/130/snapshot");

    const visitorCard = within(cards[1]);
    expect(visitorCard.getByText("1 sighting")).toBeInTheDocument();
    expect(visitorCard.getByText("Seen")).toBeInTheDocument();
    expect(visitorCard.getAllByRole("img")).toHaveLength(1);

    expect(requests[0].get("review_status")).toBe("pending");
    expect(requests[0].get("page")).toBe("1");
    expect(requests[0].get("page_size")).toBe("12");
  });

  it("shows a clear placeholder when a snapshot is not available", async () => {
    serveGroups(() =>
      groupsPage([group(5, [6, 5], { samples: [face(6), face(5, { snapshot_available: false })] })]),
    );
    renderWithProviders(<UnknownFacesPage />, { route: "/unknown-faces" });

    const placeholder = await screen.findByRole("img", { name: /\(No photo\)$/ });
    expect(placeholder.tagName).toBe("DIV");
    expect(within(placeholder).getByText("No photo")).toBeInTheDocument();
    const photos = screen.getAllByRole("img").filter((element) => element.tagName === "IMG");
    expect(photos.map((element) => element.getAttribute("src"))).toEqual(["/api/v1/unknown-faces/6/snapshot"]);
  });

  it("pages over groups, not faces", async () => {
    const requests = serveGroups((params) =>
      params.get("page") === "2"
        ? groupsPage([group(50, ids(50, 52))], { total: 30, pageNumber: 2 })
        : groupsPage([owner], { total: 30 }),
    );
    renderWithProviders(<UnknownFacesPage />, { route: "/unknown-faces" });

    expect(await screen.findByText("30 sightings")).toBeInTheDocument();
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("3 sightings")).toBeInTheDocument();
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
    expect(screen.queryByText("30 sightings")).not.toBeInTheDocument();
    expect(requests.at(-1)?.get("page")).toBe("2");
  });

  it("moves back to the last page when the current page has no groups left", async () => {
    const requests = serveGroups((params) =>
      params.get("page") === "3" ? groupsPage([], { total: 13, pageNumber: 3 }) : groupsPage([owner], { total: 13, pageNumber: 2 }),
    );
    renderWithProviders(<UnknownFacesPage />, { route: "/unknown-faces?page=3" });

    expect(await screen.findByText("30 sightings")).toBeInTheDocument();
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
    expect(requests.map((params) => params.get("page"))).toEqual(["3", "2"]);
  });

  it("notes when only the newest faces were grouped", async () => {
    serveGroups(() => groupsPage([owner], { facesTotal: 6200 }));
    renderWithProviders(<UnknownFacesPage />, { route: "/unknown-faces" });

    expect(await screen.findByRole("note")).toHaveTextContent("Only the newest 30 of 6200 faces are grouped.");
  });

  it("keeps filters in the URL and shows reviewed groups without actions", async () => {
    const requests = serveGroups(() =>
      groupsPage([group(9, [9, 8], { pending_count: 0, samples: [face(9, { review_status: "assigned" })] })]),
    );
    renderWithProviders(<UnknownFacesPage />, { route: "/unknown-faces?review_status=assigned&camera_id=3" });

    const card = await screen.findByRole("article");
    expect(within(card).getByText("Assigned")).toBeInTheDocument();
    expect(within(card).queryByRole("button")).not.toBeInTheDocument();
    expect(requests[0].get("review_status")).toBe("assigned");
    expect(requests[0].get("camera_id")).toBe("3");
  });

  it("assigns the faces the reviewer kept ticked in one request, adding to the gallery by default", async () => {
    const warning = vi.spyOn(toast, "warning");
    const requests = serveGroups(() => groupsPage([owner]));
    server.use(http.get("*/api/v1/employees", () => HttpResponse.json(page([employee()]))));
    const bodies = captureBulk(
      bulkResult({
        processed_ids: ids(101, 130).filter((id) => id !== 129 && id !== 101 && id !== 102),
        skipped: [{ id: 102, reason: "already_reviewed" }],
        attendance_updated: true,
        gallery_face_id: 130,
        gallery_rejection_reason: "too_blurry",
      }),
      "27 unknown face(s) assigned. 1 skipped (already reviewed or not found).",
    );
    renderWithProviders(<UnknownFacesPage />, { route: "/unknown-faces" });

    await userEvent.click(await screen.findByRole("button", { name: "Assign" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Assign 30 faces to an employee" }));
    expect(dialog.getAllByRole("checkbox", { name: /^Include face/ })).toHaveLength(24);
    // Untick one face on the first page and the last face on the second page.
    await userEvent.click(dialog.getByRole("checkbox", { name: "Include face 2 of 30" }));
    await userEvent.click(dialog.getByRole("button", { name: "Next faces" }));
    expect(dialog.getByText("25–30 of 30")).toBeInTheDocument();
    await userEvent.click(dialog.getByRole("checkbox", { name: "Include face 30 of 30" }));
    expect(dialog.getByText("28 of 30 faces ticked")).toBeInTheDocument();

    await userEvent.click(dialog.getByRole("combobox", { name: "Employee" }));
    await userEvent.click(await screen.findByRole("option", { name: /Ayesha Khan \(E-041\)/ }));
    // Q64: adding to the gallery is the default; the reviewer can untick it.
    expect(dialog.getByRole("checkbox", { name: /gallery as assigned photos/ })).toBeChecked();
    await userEvent.click(dialog.getByRole("button", { name: "Assign 28 faces" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(bodies).toEqual([
      {
        action: "assign",
        face_ids: ids(101, 130).filter((id) => id !== 129 && id !== 101),
        employee_id: 41,
        add_to_gallery: true,
      },
    ]);
    expect(warning).toHaveBeenCalledWith("27 unknown face(s) assigned. 1 skipped (already reviewed or not found).", {
      description: "Skipped faces: 1 already reviewed.",
    });
    expect(warning).toHaveBeenCalledWith("Assigned, but not added to the gallery: too blurry");
    await waitFor(() => expect(requests.length).toBeGreaterThan(1)); // the queue is refetched
  });

  it("shows a consent error under the gallery option and keeps the dialog open", async () => {
    serveGroups(() => groupsPage([visitor]));
    server.use(
      http.get("*/api/v1/employees", () => HttpResponse.json(page([employee({ consent_signed_at: null })]))),
      http.post("*/api/v1/unknown-faces/bulk", () =>
        HttpResponse.json(
          {
            success: false,
            message: "Enrollment requires the employee's recorded consent.",
            errors: { consent_signed_at: ["Record the signed consent date before enrolling faces."] },
          },
          { status: 422 },
        ),
      ),
    );
    renderWithProviders(<UnknownFacesPage />, { route: "/unknown-faces" });

    await userEvent.click(await screen.findByRole("button", { name: "Assign" }));
    const dialog = within(await screen.findByRole("dialog"));
    await userEvent.click(dialog.getByRole("combobox", { name: "Employee" }));
    await userEvent.click(await screen.findByRole("option", { name: /Ayesha Khan/ }));
    // Q64: adding to the gallery is the default; the reviewer can untick it.
    expect(dialog.getByRole("checkbox", { name: /gallery as assigned photos/ })).toBeChecked();
    await userEvent.click(dialog.getByRole("button", { name: "Assign 1 face" }));

    expect(await dialog.findByRole("alert")).toHaveTextContent("Record the signed consent date before enrolling faces.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("dismisses every face of a card after confirmation and reports skipped faces", async () => {
    const warning = vi.spyOn(toast, "warning");
    serveGroups(() => groupsPage([group(1, [3, 2, 1])]));
    const bodies = captureBulk(
      bulkResult({ action: "dismiss", processed_ids: [3, 2], skipped: [{ id: 1, reason: "not_found" }] }),
      "2 unknown face(s) dismissed. 1 skipped (already reviewed or not found).",
    );
    renderWithProviders(<UnknownFacesPage />, { route: "/unknown-faces" });

    await userEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    const confirm = within(await screen.findByRole("alertdialog", { name: "Dismiss all 3 faces in this group?" }));
    expect(bodies).toEqual([]); // nothing is sent before the confirmation
    await userEvent.click(confirm.getByRole("button", { name: "Dismiss" }));

    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(bodies).toEqual([{ action: "dismiss", face_ids: [3, 2, 1] }]);
    expect(warning).toHaveBeenCalledWith("2 unknown face(s) dismissed. 1 skipped (already reviewed or not found).", {
      description: "Skipped faces: 1 not found.",
    });
  });

  it("lets an operator dismiss but not assign", async () => {
    const operator: UserProfile = {
      ...hrUser,
      role: "operator",
      permissions: hrUser.permissions.filter((permission) => permission !== "unknown_faces:assign"),
    };
    server.use(http.get("*/api/v1/auth/me", () => HttpResponse.json(ok(operator))));
    serveGroups(() => groupsPage([visitor]));
    renderWithProviders(<UnknownFacesPage />, { route: "/unknown-faces" });

    expect(await screen.findByRole("button", { name: "Dismiss" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Assign" })).not.toBeInTheDocument();
  });

  it("refreshes the groups when /ws/live reports a new unknown face", async () => {
    const requests = serveGroups(() => groupsPage([visitor]));
    const { client } = renderWithProviders(<UnknownFacesPage />, { route: "/unknown-faces" });
    await screen.findByRole("article");
    const before = requests.length;

    applyLiveMessage(
      client,
      {
        type: "RecognitionCreated",
        sent_at: "2026-10-04T08:20:00Z",
        data: {
          event_id: 1,
          camera_id: 3,
          status: "unknown",
          employee_id: null,
          employee_code: null,
          employee_name: null,
          department_id: null,
          confidence: 0.2,
          captured_at: "2026-10-04T08:20:00Z",
          bbox: null,
          snapshot_available: true,
        },
      },
      (key) => void client.invalidateQueries({ queryKey: key }),
    );
    await waitFor(() => expect(requests.length).toBeGreaterThan(before));
  });
});
