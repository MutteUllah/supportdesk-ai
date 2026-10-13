import { test, expect } from "@playwright/test";

test("registration, knowledge, citations, tickets, widget continuity and human handoff", async ({
  page,
  context,
}) => {
  const email = `browser-${Date.now()}@example.test`,
    password = "Browser-test-password-123!";
  await page.goto("/");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page.getByLabel("New workspace name").fill("Browser Outfitters");
  await page
    .getByRole("button", { name: "Create workspace", exact: true })
    .click();
  await page.getByRole("button", { name: "Documents", exact: true }).click();
  await page.getByLabel("Upload document", { exact: true }).setInputFiles({
    name: "shipping.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "Shipping takes 3 business days. Returns are accepted within 30 days with a receipt.",
    ),
  });
  await expect(page.getByText("searchable", { exact: false })).toBeVisible({
    timeout: 45000,
  });
  await page.getByRole("button", { name: "Playground", exact: true }).click();
  await page.getByRole("button", { name: "+ New conversation" }).click();
  await page
    .getByLabel("Message", { exact: true })
    .fill("How long does shipping take?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(
    page.getByText("[Mock mode — extracted evidence]", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Source · page 1" }).click();
  await expect(
    page.getByRole("dialog", { name: "Citation source" }),
  ).toContainText("3 business days");
  await page.getByRole("button", { name: "Close source" }).click();
  await page.getByRole("button", { name: "Create support ticket" }).click();
  await page.getByLabel("Subject", { exact: true }).fill("Order help");
  await page.getByLabel("Issue description").fill("Please help with my order.");
  await page.getByRole("button", { name: "Confirm & create ticket" }).click();
  await expect(page.getByText("was created.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Tickets", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Order help" })).toBeVisible();
  await page.getByLabel("Status Order help").selectOption("in progress");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page
    .getByLabel("Permitted website origins (one per line)")
    .fill("http://localhost:3001");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByText("Settings saved.")).toBeVisible();
  const snippet = await page.locator("pre").innerText();
  const publicId = snippet.match(/data-workspace="([^"]+)"/)![1];
  const demo = await context.newPage();
  await demo.goto(`http://localhost:3001/?workspace=${publicId}`);
  await demo.getByRole("button", { name: "Chat with support" }).click();
  const frame = demo.frameLocator('iframe[title="Customer support chat"]');
  await frame
    .getByRole("textbox", { name: "Message", exact: true })
    .fill("What is the returns policy?");
  await frame.getByRole("button", { name: "Send", exact: true }).click();
  await expect(
    frame.getByText("[Mock mode — extracted evidence]", { exact: false }),
  ).toBeVisible();
  await demo.reload();
  await demo.getByRole("button", { name: "Chat with support" }).click();
  await expect(
    frame.getByText("[Mock mode — extracted evidence]", { exact: false }),
  ).toBeVisible();
  await frame.getByRole("button", { name: "Request human" }).click();
  await expect(
    frame.getByText("Waiting for a human.", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Support inbox", exact: true })
    .click();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await page.locator(".conversation-list button").first().click();
  await page.getByRole("button", { name: "Claim conversation" }).click();
  await page
    .getByLabel("Message", { exact: true })
    .fill("Hello from your human support agent.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(
    frame.getByText("Hello from your human support agent.", { exact: true }),
  ).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: "Return to bot" }).click();
  await expect(frame.getByText("Assistant ready", { exact: true })).toBeVisible(
    { timeout: 15000 },
  );
  await page.getByRole("button", { name: "Log out", exact: true }).click();
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page.getByLabel("Workspace", { exact: true })).toContainText(
    "Browser Outfitters",
  );
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await page.screenshot({
    path: "test-results/dashboard-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/dashboard-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
