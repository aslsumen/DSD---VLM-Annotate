// Build the frontend first. Set PLAYWRIGHT_MODULE to a local Playwright installation.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { preview } from "vite";

const require = createRequire(import.meta.url);
const { chromium, webkit } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const server = await preview({
  configFile: false,
  root: fileURLToPath(new URL("../", import.meta.url)),
  preview: { host: "127.0.0.1", port: 0 },
});
const base = "http://127.0.0.1:" + server.httpServer.address().port;
const key = "vlm-annotate.api-token";
const user = { id: 1, role: "administrator", full_name: "QA One", email: "one@example.test",
  is_active: true, created_at: "2026-01-01T00:00:00Z" };
let browser;
try {
  browser = process.env.ENGINE === "webkit" ? await webkit.launch()
    : await chromium.launch({ channel: "chrome" });
  for (const action of ["retry", "sign out", "fresh login", "logout during retry"]) {
    const page = await browser.newPage();
    try {
      page.setDefaultTimeout(6000);
      await page.clock.install();
      let checks = 0;
      let revocations = 0;
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      await page.route("**/api/v1/**", async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith("/auth/me")) {
          checks++;
          if (checks === 2) return route.fulfill({ status: 503, json: {} });
          if (checks === 3 && action === "logout during retry") await gate;
          return route.fulfill({ json: user });
        }
        if (path.endsWith("/auth/logout")) {
          revocations++;
          assert.equal(route.request().headers().authorization, "Bearer qa-old");
          if (action === "fresh login") await gate;
          return route.fulfill({ status: 503, json: {} });
        }
        if (path.endsWith("/auth/login")) {
          return route.fulfill({ json: { access_token: "qa-new", expires_at: "2099-01-01T00:00:00Z",
            token_type: "bearer", user: { ...user, id: 2, full_name: "QA Two" } } });
        }
        return route.fulfill({ json: [] });
      });
      await page.goto(base);
      await page.evaluate(key => localStorage.setItem(key, "qa-old"), key);
      await page.goto(base + "/#/users");
      await page.reload();
      const heading = name => page.getByRole("heading", { name, exact: true });
      await heading("Users").waitFor();
      await page.clock.fastForward(30100);
      await heading("Authentication unavailable").waitFor();
      assert.equal(await page.evaluate(key => localStorage.getItem(key), key), "qa-old");
      if (action === "retry") {
        await page.getByRole("button", { name: "Try again" }).click();
        await heading("Users").waitFor();
        assert.equal(checks, 3);
        assert.equal(revocations, 0);
      } else {
        if (action === "logout during retry") {
          const checking = page.waitForRequest("**/auth/me");
          await page.getByRole("button", { name: "Try again" }).click();
          await checking;
        }
        const revoke = page.waitForRequest("**/auth/logout");
        if (action === "fresh login") await page.getByRole("link", { name: "Go to sign in" }).click();
        else await page.getByRole("button", { name: "Sign out", exact: true }).click();
        await revoke;
        await heading("Sign in").waitFor();
        assert.equal(await page.evaluate(key => localStorage.getItem(key), key), null);
        if (action === "fresh login") {
          await page.locator("#signin-email").fill("two@example.test");
          await page.locator("#signin-password").fill("synthetic");
          await page.getByRole("button", { name: "Sign in", exact: true }).click();
          await page.getByText("QA Two", { exact: true }).waitFor();
          const settled = page.waitForResponse("**/auth/logout");
          release();
          await settled;
          await page.getByText("QA Two", { exact: true }).waitFor();
          assert.equal(await page.evaluate(key => localStorage.getItem(key), key), "qa-new");
        } else {
          release();
          await page.getByText(/Server sign-out could not be confirmed/).waitFor();
          const count = checks;
          await page.clock.fastForward(95000);
          await heading("Sign in").waitFor();
          assert.equal(checks, count);
          assert.equal(await page.evaluate(key => localStorage.getItem(key), key), null);
        }
        assert.equal(revocations, 1);
      }
      console.log("PASS", action, browser.version());
    } finally {
      await page.close();
    }
  }
} finally {
  await browser?.close();
  await server.close();
}
