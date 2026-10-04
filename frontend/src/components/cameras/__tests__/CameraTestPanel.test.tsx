import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CameraTestPanel } from "@/components/cameras/CameraTestPanel";
import { connectionHint } from "@/lib/cameraHints";

describe("connectionHint", () => {
  it("explains a 401 from the camera (seen with a Dahua camera)", () => {
    expect(
      connectionHint("HTTPUnauthorizedError: [Errno 825242872] Server returned 401 Unauthorized (authorization failed): '<url>'"),
    ).toMatch(/username or password/);
  });

  it("explains a 403 from the camera (locked account, seen with a Dahua camera)", () => {
    expect(
      connectionHint("HTTPForbiddenError: [Errno 858797304] Server returned 403 Forbidden (access denied): '<url>'"),
    ).toMatch(/lock the account/);
  });

  it("explains a wrong stream path and an unreachable camera", () => {
    expect(connectionHint("Server returned 404 Not Found")).toMatch(/stream path/);
    expect(connectionHint("OSError: [Errno 113] No route to host")).toMatch(/cannot reach/);
  });

  it("has no hint for other errors", () => {
    expect(connectionHint("InvalidDataError: something else")).toBeNull();
  });
});

describe("CameraTestPanel", () => {
  it("shows the raw error and the hint", () => {
    render(
      <CameraTestPanel
        result={{ ok: false, error: "Server returned 401 Unauthorized", width: null, height: null, codec: null, snapshot_jpeg_b64: null } as never}
        pending={false}
        onTest={() => {}}
      />,
    );
    expect(screen.getByText("Connection failed")).toBeInTheDocument();
    expect(screen.getByText("Server returned 401 Unauthorized")).toBeInTheDocument();
    expect(screen.getByText(/username or password/)).toBeInTheDocument();
  });

  it("blocks the test and says why while a typed link is not saved", () => {
    render(<CameraTestPanel result={null} pending={false} onTest={() => {}} disabledReason="Save changes first." />);
    expect(screen.getByRole("button", { name: /test connection/i })).toBeDisabled();
    expect(screen.getByText("Save changes first.")).toBeInTheDocument();
  });
});
