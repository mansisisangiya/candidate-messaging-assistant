import { expect, test } from "@playwright/test";

test("recruiter drafts a reply for Priya and approves it", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("conversation-item").filter({ hasText: "Priya Sharma" }).click();
  await expect(page.getByRole("heading", { name: "Priya Sharma" })).toBeVisible();

  await page.getByTestId("draft-button").click();

  const draft = page.getByRole("textbox", { name: /you can edit it/i });
  await expect(page.getByTestId("run-status")).toHaveText("awaiting approval");
  await expect(draft).toContainText("2026-11-12 at 14:00 UTC with Daniel Okafor");

  const steps = page.getByTestId("trace-step");
  await expect(steps).toHaveCount(7);
  await expect(steps.nth(0)).toContainText("get_candidate");
  await expect(steps.nth(2)).toContainText("get_interview_status");
  await expect(page.getByTestId("degraded-banner")).toHaveCount(0);

  // Optional: save the documentation screenshot (E2E_SCREENSHOT=path/to/file.png).
  if (process.env.E2E_SCREENSHOT) {
    await page.getByRole("region", { name: "Draft" }).screenshot({ path: process.env.E2E_SCREENSHOT });
  }

  await page.getByTestId("approve-button").click();

  await expect(page.getByTestId("run-status")).toHaveText("approved");
  await expect(page.getByText("Approved - ready to send")).toBeVisible();
  await expect(page.getByTestId("approve-button")).toHaveCount(0);
  // The list badge follows.
  await expect(
    page.getByTestId("conversation-item").filter({ hasText: "Priya Sharma" }).getByTestId("status-badge"),
  ).toHaveText("approved");
});
