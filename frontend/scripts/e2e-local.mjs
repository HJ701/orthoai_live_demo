import { chromium, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

const baseUrl = process.env.E2E_BASE_URL || "http://127.0.0.1:3000";
const email = process.env.E2E_EMAIL || `e2e-${Date.now()}@orthoai.co`;
const artifactDir = join(process.cwd(), "e2e-artifacts");
const pngPath = join(artifactDir, "orthoai-e2e.png");

const tinyPngBase64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=";

async function main() {
  await mkdir(artifactDir, { recursive: true });
  await writeFile(pngPath, Buffer.from(tinyPngBase64, "base64"));

  const browser = await chromium.launch({ headless: process.env.E2E_HEADLESS !== "false" });
  const page = await browser.newPage();
  page.setDefaultTimeout(45_000);

  try {
    await page.goto(baseUrl, { waitUntil: "networkidle" });

    await page.getByLabel("Email address").fill(email);
    await page.getByRole("button", { name: "Send OTP" }).click();
    const devOtp = (await page.getByTestId("dev-otp-code").textContent())?.trim();
    if (!devOtp) throw new Error("Local E2E requires DEV_EXPOSE_OTP=true on the backend.");
    await page.getByLabel("Enter OTP Code").fill(devOtp);
    await page.getByRole("button", { name: /^Sign In$/i }).click();

    await page.waitForURL(/\/(terms|upload)/);
    if (page.url().includes("/terms")) {
      await page.getByRole("checkbox").check();
      const acceptButton = page.getByRole("button", { name: /Accept & Continue/i });
      await expect(acceptButton).toBeVisible();
      await acceptButton.click();
    }

    await expect(page).toHaveURL(/\/upload/);
    await page.getByLabel("Patient reference").fill(`E2E-${Date.now()}`);
    await page.getByLabel("Case title").fill("E2E orthodontic assessment");
    await page.getByLabel("Clinic location").fill("Local E2E clinic");
    await page.getByLabel("Clinical note").fill("Automated browser E2E upload and mock inference.");
    await page.getByLabel("Clinical image files").setInputFiles(pngPath);
    await page.getByLabel("Consent confirmation").check();
    await page.getByRole("button", { name: /Run Analysis/i }).click();

    await page.waitForURL(/\/results\?case_id=/, { timeout: 90_000 });
    await expect(page.getByRole("heading", { name: "Diagnostic Summary" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Evidence & Visuals" })).toBeVisible();
    await page.getByRole("main").getByRole("button", { name: /^Clinical Validation$/i }).click();

    await expect(page).toHaveURL(/\/clinical\?case_id=/);
    await page.getByLabel("Site").fill("E2E");
    await page.getByLabel("Validation case ID").fill(`E2E-VAL-${Date.now()}`);
    await page.getByLabel("Clinician").fill("E2E clinician");
    await page.getByLabel("Manual class").selectOption("Class I");
    await page.getByRole("spinbutton", { name: "DHC" }).fill("4");
    await page.getByRole("spinbutton", { name: "AC" }).fill("6");
    await page.getByRole("spinbutton", { name: "Manual time minutes" }).fill("3.5");
    await page.getByRole("spinbutton", { name: "Useful score" }).fill("5");
    await page.getByLabel("Clinical comment").fill("Automated validation record created by browser E2E.");
    await page.getByRole("button", { name: /Save Validation/i }).click();
    await expect(page.getByText("Clinical validation saved.")).toBeVisible();

    await page.goto(`${baseUrl}/account`, { waitUntil: "networkidle" });
    await expect(page.getByText(email)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Audit Log", exact: true })).toBeVisible();
    await expect(page.getByText("Clinical Validations")).toBeVisible();

    await page.goto(`${baseUrl}/help`, { waitUntil: "networkidle" });
    const support = page.getByRole("link", { name: /Contact Support/i });
    await expect(support).toHaveAttribute("href", /mailto:Info@orthoai\.co/i);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
