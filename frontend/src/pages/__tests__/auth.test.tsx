import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { LoginPage } from "@/pages/login/LoginPage";
import { ProtectedRoute, RequirePermission } from "@/routes/guards";
import { visibleNavItems } from "@/routes/navigation";
import { employeeUser, hrUser, ok } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";

const anonymous = http.get("*/api/v1/auth/me", () =>
  HttpResponse.json({ success: false, message: "Not signed in.", errors: {} }, { status: 401 }),
);

describe("sign-in (§13 screen 1, FR-40)", () => {
  it("signs in and returns to the page the user asked for", async () => {
    server.use(anonymous);
    let body: unknown = null;
    server.use(
      http.post("*/api/v1/auth/login", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(ok(hrUser, "Signed in."));
      }),
    );
    renderWithProviders(<LoginPage />, {
      route: "/login?next=%2Fattendance",
      path: "/login",
      extraRoutes: [{ path: "/attendance", element: <p>Attendance screen</p> }],
    });
    await userEvent.type(await screen.findByLabelText("Username"), "hina");
    await userEvent.type(screen.getByLabelText("Password"), "Correct-horse-42");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Attendance screen")).toBeInTheDocument();
    expect(body).toEqual({ username: "hina", password: "Correct-horse-42", provider: "local" });
  });

  it("shows the API's message on a failed sign-in and never follows an external next URL", async () => {
    server.use(
      anonymous,
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json({ success: false, message: "Invalid username or password.", errors: {} }, { status: 401 }),
      ),
    );
    renderWithProviders(<LoginPage />, { route: "/login?next=//evil.example", path: "/login" });
    await userEvent.type(await screen.findByLabelText("Username"), "hina");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password.");
  });

  it("validates before calling the API and focuses the first empty field", async () => {
    server.use(anonymous);
    renderWithProviders(<LoginPage />, { route: "/login", path: "/login" });
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your username")).toBeInTheDocument();
    expect(screen.getByLabelText("Username")).toHaveFocus(); // refs reach the input (React 18)
  });

  it("offers Active Directory only when it is enabled", async () => {
    server.use(anonymous, http.get("*/api/v1/auth/options", () => HttpResponse.json(ok({ ldap_enabled: true }))));
    renderWithProviders(<LoginPage />, { route: "/login", path: "/login" });
    expect(await screen.findByRole("button", { name: /Sign in with Active Directory/ })).toBeInTheDocument();
  });
});

describe("route guards (§4)", () => {
  it("sends signed-out users to sign-in with a return path", async () => {
    server.use(anonymous);
    renderWithProviders(
      <ProtectedRoute>
        <p>Secret</p>
      </ProtectedRoute>,
      { route: "/employees?search=ali", path: "/employees", extraRoutes: [{ path: "/login", element: <p>Login page</p> }] },
    );
    expect(await screen.findByText("Login page")).toBeInTheDocument();
    expect(screen.queryByText("Secret")).not.toBeInTheDocument();
  });

  it("hides screens the role may not use", async () => {
    server.use(http.get("*/api/v1/auth/me", () => HttpResponse.json(ok(employeeUser))));
    renderWithProviders(
      <RequirePermission anyOf={["employees:manage"]}>
        <p>Employees</p>
      </RequirePermission>,
    );
    expect(await screen.findByText("You do not have access to this page")).toBeInTheDocument();
  });

  it("shows each role only its own menu", () => {
    const can = (perms: string[]) => (p: string) => perms.includes(p);
    expect(visibleNavItems(can(employeeUser.permissions), true).map((i) => i.to)).toEqual(["/me"]);
    const hrMenu = visibleNavItems(can(hrUser.permissions), false).map((i) => i.to);
    expect(hrMenu).toContain("/employees");
    expect(hrMenu).not.toContain("/settings");
    expect(hrMenu).not.toContain("/me");
  });
});

describe("session expiry", () => {
  it("returns to sign-in when an API call says the session ended", async () => {
    let calls = 0;
    server.use(
      http.get("*/api/v1/auth/me", () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(ok(hrUser))
          : HttpResponse.json({ success: false, message: "Session expired.", errors: {} }, { status: 401 });
      }),
    );
    const { client } = renderWithProviders(
      <ProtectedRoute>
        <p>Inside</p>
      </ProtectedRoute>,
      { route: "/dashboard", path: "/dashboard", extraRoutes: [{ path: "/login", element: <p>Login page</p> }] },
    );
    expect(await screen.findByText("Inside")).toBeInTheDocument();
    await client.invalidateQueries({ queryKey: ["auth", "me"] });
    await waitFor(() => expect(screen.getByText("Login page")).toBeInTheDocument());
  });
});

describe("sign out", () => {
  it("ends on the sign-in page and stays there", async () => {
    let signedIn = true;
    server.use(
      http.get("*/api/v1/auth/me", () =>
        signedIn
          ? HttpResponse.json(ok(hrUser))
          : HttpResponse.json({ success: false, message: "Not signed in.", errors: {} }, { status: 401 }),
      ),
      http.post("*/api/v1/auth/logout", () => {
        signedIn = false;
        return HttpResponse.json(ok(null, "Signed out."));
      }),
    );
    const { UserMenu } = await import("@/components/layout/UserMenu");
    renderWithProviders(
      <ProtectedRoute>
        <UserMenu />
      </ProtectedRoute>,
      { route: "/dashboard", path: "/dashboard", extraRoutes: [{ path: "/login", element: <LoginPage /> }] },
    );
    await userEvent.click(await screen.findByRole("button", { name: "Account menu" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Sign out" }));
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });
});
