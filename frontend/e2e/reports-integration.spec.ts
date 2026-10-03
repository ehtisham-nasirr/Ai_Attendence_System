import { expect, test } from "@playwright/test";

/** Phase 4 through the browser against the real backend and Celery worker: report preview, Excel/PDF
 * download from the export job, and an API key used on the payroll pull API (FR-30..FR-35). */

const username = process.env.E2E_USERNAME ?? "";
const password = process.env.E2E_PASSWORD ?? "";
const shots = process.env.E2E_SCREENSHOT_DIR;

test.skip(!username || !password, "E2E_USERNAME and E2E_PASSWORD are required");

test("reports preview, export download and payroll API key", async ({ page, request }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);

  const today = new Date().toISOString().slice(0, 10);
  await page.goto(`/reports?type=daily&from=${today.slice(0, 8)}01&to=${today}`);
  await page.getByRole("button", { name: "Run report" }).click();
  await expect(page.getByText("Days", { exact: true })).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  if (shots) await page.screenshot({ path: `${shots}/12-reports.png`, fullPage: true });

  for (const [button, extension] of [
    ["Export Excel", "xlsx"],
    ["Export PDF", "pdf"],
  ] as const) {
    const downloadPromise = page.waitForEvent("download", { timeout: 60_000 });
    await page.getByRole("button", { name: button }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(new RegExp(`^facetrack-daily-\\d{8}-\\d{8}\\.${extension}$`));
    const path = await download.path();
    expect(path).toBeTruthy();
  }

  // API key: created in Settings › Integration, then used by "payroll" on the pull API.
  await page.goto("/settings?tab=integration");
  await page.getByLabel("New key for").fill(`E2E payroll ${Date.now()}`);
  await page.getByRole("button", { name: "Create key" }).click();
  const key = await page.getByRole("dialog").getByRole("textbox").inputValue();
  expect(key).toMatch(/^ft_[0-9a-f]{8}_/);
  await page.getByRole("button", { name: "Done" }).click();
  if (shots) await page.screenshot({ path: `${shots}/13-settings-integration.png`, fullPage: true });

  const pulled = await request.get(`/api/v1/integration/attendance?date=${today}`, { headers: { "X-API-Key": key } });
  expect(pulled.status()).toBe(200);
  expect((await pulled.json()).success).toBe(true);
  const rejected = await request.get(`/api/v1/integration/attendance?date=${today}`, { headers: { "X-API-Key": "ft_bad_key" } });
  expect(rejected.status()).toBe(401);

  expect(errors).toEqual([]);
});
