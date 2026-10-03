import { expect, test, type Page } from "@playwright/test";

/**
 * Walks every §13 screen as a Super Admin against a real backend and creates test data along the way
 * (location, department, shift, employee, leave, manual attendance, correction). Needs:
 *   E2E_USERNAME / E2E_PASSWORD  — an existing Super Admin (never a production account)
 * Optional: E2E_SCREENSHOT_DIR to keep a screenshot of each screen.
 */

const username = process.env.E2E_USERNAME ?? "";
const password = process.env.E2E_PASSWORD ?? "";
const shots = process.env.E2E_SCREENSHOT_DIR;
const run = Date.now().toString(36).toUpperCase();

test.skip(!username || !password, "E2E_USERNAME and E2E_PASSWORD are required");

async function snap(page: Page, name: string) {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
}

function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    // Missing snapshots (retention) and the absent MediaMTX in dev are expected network failures.
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource")) {
      errors.push(`console: ${message.text()}`);
    }
  });
  return errors;
}

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function chooseOption(page: Page, trigger: string, option: string) {
  await page.getByRole("combobox", { name: trigger }).click();
  await page.getByRole("option", { name: option }).click();
}

test("Super Admin works through every screen", async ({ page }) => {
  const errors = trackErrors(page);
  await signIn(page);

  // Dashboard (screen 2)
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Present", { exact: true }).first()).toBeVisible();
  await snap(page, "02-dashboard");

  // Settings: organization, shift (screen 13)
  await page.goto("/settings?tab=organization");
  await page.getByRole("button", { name: "Add location" }).click();
  await page.getByLabel("Name").fill(`E2E Office ${run}`);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: `E2E Office ${run}` })).toBeVisible();
  await page.getByRole("button", { name: "Add department" }).click();
  await page.getByLabel("Name").fill(`E2E Dept ${run}`);
  await page.getByLabel("Code (used in imports)").fill(`E2E${run}`);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: `E2E Dept ${run}` })).toBeVisible();
  await snap(page, "13-settings-organization");

  await page.getByRole("tab", { name: "Shifts" }).click();
  await page.getByRole("button", { name: "Add shift" }).click();
  await page.getByLabel("Name").fill(`E2E Day ${run}`);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: `E2E Day ${run}` })).toBeVisible();

  for (const tab of ["General", "Holidays", "Recognition", "Retention", "Notifications", "Integration", "Users and roles"]) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("tab", { name: tab })).toHaveAttribute("data-state", "active");
  }
  await expect(page.getByRole("table")).toBeVisible();
  await snap(page, "13-settings-users");

  // Employees: create and open the profile (screens 4, 5)
  await page.goto("/employees");
  await expect(page.getByRole("heading", { name: "Employees" })).toBeVisible();
  await page.getByRole("button", { name: "Add employee" }).first().click();
  const drawer = page.getByRole("dialog");
  await drawer.getByLabel("Employee code").fill(`E2E-${run}`);
  await drawer.getByLabel("Full name").fill(`Test Person ${run}`);
  await drawer.getByLabel("Department").click();
  await page.getByRole("option", { name: `E2E Dept ${run}` }).click();
  await drawer.getByLabel("Shift").click();
  await page.getByRole("option", { name: `E2E Day ${run}` }).click();
  await drawer.getByLabel("Location").click();
  await page.getByRole("option", { name: `E2E Office ${run}` }).click();
  await drawer.getByLabel("Biometric consent signed on").fill(new Date().toISOString().slice(0, 10));
  await drawer.getByRole("button", { name: "Add employee" }).click();
  await expect(page.getByRole("heading", { name: `Test Person ${run}` })).toBeVisible();
  await expect(page.getByText("Not enrolled")).toBeVisible();
  await snap(page, "05-employee-details");

  await page.getByRole("tab", { name: "Face gallery" }).click();
  await expect(page.getByText("No face photos yet")).toBeVisible();
  await page.getByRole("tab", { name: "Enroll" }).click();
  await expect(page.getByText("Drop photos here or click to choose")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Enroll", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tab", { name: "Face gallery" })).toHaveAttribute("aria-selected", "false");
  await snap(page, "05-employee-enroll");
  await page.getByRole("tab", { name: "Attendance history" }).click();
  await expect(page.getByText("Mon", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Leave" }).click();
  await page.getByLabel("From", { exact: true }).fill("2026-01-05");
  await page.getByLabel("To", { exact: true }).fill("2026-01-06");
  await page.getByRole("button", { name: "Add leave" }).click();
  await expect(page.getByText("Entered manually")).toBeVisible();

  // Attendance: manual entry, then a correction (screen 7)
  await page.goto("/attendance");
  await expect(page.getByRole("heading", { name: "Attendance" })).toBeVisible();
  await page.getByRole("button", { name: "Add manual entry" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("combobox").first().click();
  await page.getByPlaceholder("Search name or code…").fill(`E2E-${run}`);
  await page.getByRole("option", { name: new RegExp(`E2E-${run}`) }).click();
  await dialog.getByLabel("Check-in").fill("09:05");
  await dialog.getByLabel("Reason").fill("E2E test entry");
  await dialog.getByRole("button", { name: "Add entry" }).click();
  await expect(page.getByRole("cell", { name: new RegExp(`Test Person ${run}`) }).first()).toBeVisible();
  await snap(page, "07-attendance");

  await page.getByRole("button", { name: `Correct attendance of Test Person ${run}` }).click();
  await chooseOption(page, "What is wrong?", "Status");
  await chooseOption(page, "Correct status", "Present");
  await page.getByRole("dialog").getByLabel("Reason").fill("E2E correction check");
  await page.getByRole("button", { name: "Apply correction" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();

  // Monthly register (screen 8)
  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "Monthly register" })).toBeVisible();
  await page.getByLabel("Search name or code").fill(`E2E-${run}`);
  await expect(page.getByRole("cell", { name: new RegExp(`Test Person ${run}`) }).first()).toBeVisible();
  await snap(page, "08-register");

  // Corrections (screen 11): the applied correction is listed as approved
  await page.goto("/corrections?status=approved");
  await expect(page.getByText(`Test Person ${run}`).first()).toBeVisible();
  await snap(page, "11-corrections");

  // Remaining screens load without errors (3, 6, 9, 10, 14)
  for (const [path, heading, shot] of [
    ["/live", "Live view", "03-live"],
    ["/cameras", "Cameras", "06-cameras"],
    ["/unknown-faces", "Unknown faces", "09-unknown"],
    ["/events", "Event log", "10-events"],
    ["/audit", "Audit log", "14-audit"],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await snap(page, shot);
  }
  await page.getByPlaceholder("Action, e.g. employee.update").fill("employee.create");
  await expect(page.getByRole("cell", { name: "employee.create" }).first()).toBeVisible();

  // Sign out
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);

  expect(errors).toEqual([]);
});

test("navigation works as a drawer on tablets @tablet", async ({ page }) => {
  const errors = trackErrors(page);
  await signIn(page);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Employees" }).click();
  await expect(page.getByRole("heading", { name: "Employees" })).toBeVisible();
  await snap(page, "tablet-employees");
  expect(errors).toEqual([]);
});
