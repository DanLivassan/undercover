import { expect, test } from "@playwright/test";
import { backendUrl, startScenario } from "./scenario";

test("the queue shows live agent activity and a paid approval", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: /CLM-1001/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /CLM-/ })).toHaveCount(25);
  const agent = startScenario("CLM-1001", "approve", "420.00", true);
  try {
    await agent.ready;
    await expect(page.locator(".claim-heading .badge")).toHaveText(
      "In progress",
    );
    await expect(
      page.getByText("read_claim completed successfully.", { exact: true }),
    ).toBeVisible();
    agent.resume();
    await agent.completion;
    await expect(page.getByText(/Payment recorded/)).toBeVisible();
    await expect(
      page.getByText(
        "The evidence establishes a covered incident. The expenses are eligible.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(page.locator(".claim-heading .badge")).toHaveText("Decided");
  } finally {
    agent.stop();
  }
});

test("over-limit payment is blocked until a handler authorizes it", async ({
  page,
  request,
}) => {
  const agent = startScenario("CLM-1003", "approve", "1250.00");
  await agent.completion;
  const blocked = await request.post(`${backendUrl}/api/claims/CLM-1003/pay`, {
    data: { amount: "1250.00" },
  });
  expect(blocked.status()).toBe(409);
  await page.goto("/");
  await page.getByRole("button", { name: /CLM-1003/ }).click();
  await expect(page.locator(".claim-heading .badge")).toHaveText(
    "Waiting for sign-off",
  );
  await expect(
    page.getByRole("button", { name: "Authorize and pay" }),
  ).toBeDisabled();
  await page.getByRole("combobox", { name: "Handler" }).selectOption("HND-01");
  await page.getByRole("button", { name: "Authorize and pay" }).click();
  await expect(page.getByText(/Payment recorded/)).toContainText("$1,250.00");
  const repeat = await request.post(`${backendUrl}/api/claims/CLM-1003/pay`, {
    data: { amount: "1250.00" },
  });
  expect(repeat.ok()).toBe(true);
  const events = (await (
    await request.get(`${backendUrl}/api/claims/CLM-1003/events`)
  ).json()) as { type: string }[];
  expect(events.filter((event) => event.type === "payment")).toHaveLength(1);
  await page.reload();
  await page.getByRole("button", { name: /CLM-1003/ }).click();
  await expect(page.getByText(/Payment recorded/)).toContainText("$1,250.00");
  await expect(page.getByText(/Authorized by HND-01/)).toBeVisible();
});

for (const scenario of [
  { claim: "CLM-1002", outcome: "decline", section: "9. General exclusions" },
  { claim: "CLM-1004", outcome: "refer", section: "11. How to claim" },
]) {
  test(`the dashboard shows a ${scenario.outcome} without payment`, async ({
    page,
  }) => {
    const agent = startScenario(scenario.claim, scenario.outcome, "0.00");
    await agent.completion;
    await page.goto("/");
    await page
      .getByRole("button", { name: new RegExp(scenario.claim) })
      .click();
    await expect(page.locator(".outcome")).toHaveText(
      new RegExp(scenario.outcome, "i"),
    );
    await expect(
      page.getByText(`Policy reference: ${scenario.section}`, { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Authorize and pay" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Record payment" }),
    ).toHaveCount(0);
  });
}

test("instructions match the API and are read only", async ({
  page,
  request,
}) => {
  const instructions = (await (
    await request.get(`${backendUrl}/api/agent/instructions`)
  ).json()) as { text: string };
  await page.goto("/");
  await page
    .getByRole("button", { name: "Agent instructions", exact: true })
    .click();
  await expect(page.locator("pre")).toHaveText(instructions.text);
  await expect(page.getByRole("textbox")).toHaveCount(0);
});

test("mobile layout and keyboard navigation remain usable", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => {
    errors.push(error.message);
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Claims queue" }),
  ).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: /CLM-1003/ }).click();
  await expect(page.getByText(/Payment recorded/)).toContainText("$1,250.00");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
