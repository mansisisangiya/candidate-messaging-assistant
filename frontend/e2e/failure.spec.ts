import { expect, test } from "@playwright/test";

// This project's backend runs with INJECT_INTERVIEW_FAILURE_FOR=cand_priya.
test("interview outage: the draft is still produced, with a warning and two error steps", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("conversation-item").filter({ hasText: "Priya Sharma" }).click();
  await page.getByTestId("draft-button").click();

  await expect(page.getByTestId("run-status")).toHaveText("awaiting approval");
  await expect(page.getByTestId("degraded-banner")).toContainText(
    "Some data was unavailable; the draft avoids relying on it.",
  );
  await expect(page.getByTestId("trace-step").filter({ hasText: "retrying" })).toHaveCount(1);
  await expect(page.locator(".step-error")).toHaveCount(2);

  const draft = page.getByRole("textbox", { name: /you can edit it/i });
  await expect(draft).not.toContainText("2026-11-12");
  await expect(draft).toContainText("will confirm them shortly");
});
